"""PII gate — block or redact before embed/store."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from app.models import CanonicalRecord


EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
PHONE = re.compile(r"\b(?:\+?\d{1,3}[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}\b")
SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")


@dataclass
class PiiDecision:
    allow: bool
    pii_flag: bool
    redaction_flag: bool
    confidence: float
    reasons: list[str]


class PiiGate:
    """Refuse high-confidence raw PII; allow redacted or flagged-low records."""

    def evaluate(self, record: CanonicalRecord) -> PiiDecision:
        reasons: list[str] = []
        conf = float(record.metadata.pii_confidence or 0.0)

        if record.metadata.quarantined:
            return PiiDecision(False, True, True, max(conf, 1.0), ["quarantined"])

        if record.metadata.pii_flag and not record.metadata.redaction_flag and conf >= 0.8:
            return PiiDecision(False, True, False, conf, ["high_confidence_unredacted_pii"])

        text = record.text or ""
        hits = 0
        if EMAIL.search(text):
            hits += 1
            reasons.append("email_pattern")
        if PHONE.search(text):
            hits += 1
            reasons.append("phone_pattern")
        if SSN.search(text):
            hits += 1
            reasons.append("ssn_pattern")

        if hits and not record.metadata.redaction_flag:
            return PiiDecision(False, True, False, max(conf, min(1.0, 0.5 + 0.2 * hits)), reasons)

        return PiiDecision(
            True,
            bool(record.metadata.pii_flag or hits),
            bool(record.metadata.redaction_flag),
            conf,
            reasons,
        )

    def redact_text(self, text: str) -> str:
        text = EMAIL.sub("[REDACTED_EMAIL]", text)
        text = PHONE.sub("[REDACTED_PHONE]", text)
        text = SSN.sub("[REDACTED_SSN]", text)
        return text
