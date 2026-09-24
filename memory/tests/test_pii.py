from __future__ import annotations

from datetime import datetime, timezone

from app.models import CanonicalRecord, Metadata, Provenance
from app.pii.gate import PiiGate


def _rec(text: str, **meta) -> CanonicalRecord:
    m = {
        "project_id": "highlightai-pending",
        "pii_flag": False,
        "redaction_flag": False,
        "quarantined": False,
    }
    m.update(meta)
    return CanonicalRecord(
        id="r1",
        text=text,
        provenance=Provenance(
            source_url="https://example.com",
            crawl_timestamp=datetime.now(timezone.utc),
        ),
        metadata=Metadata(**m),
    )


def test_blocks_email_pii():
    gate = PiiGate()
    d = gate.evaluate(_rec("Contact me at alice@example.com please"))
    assert d.allow is False
    assert "email_pattern" in d.reasons


def test_allows_clean_text():
    gate = PiiGate()
    d = gate.evaluate(_rec("No personal data here."))
    assert d.allow is True


def test_blocks_quarantined():
    gate = PiiGate()
    d = gate.evaluate(_rec("ok", quarantined=True))
    assert d.allow is False
