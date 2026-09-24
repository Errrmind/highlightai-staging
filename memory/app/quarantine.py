"""RW-1 quarantine + PII enforcement for the served /memory/* API.

Root of trust is the in-image constant set below (ships in the Docker image,
so a fresh Railway volume can never drop the blocks). On startup a manifest of
the hard-block ids (ids only, no record text) is seeded into
CLEANER_QUARANTINE_DIR on the /data volume, and any extra ids found in
*.json / *.jsonl files in that dir are unioned in (quarantine-skip).

PII gate (mirrors app/pii/gate.py, threshold 0.80):
  - metadata.quarantined == true                          -> refused
  - pii_flag and not redaction_flag and pii_confidence>=0.80 -> refused
  - unredacted email / phone / SSN pattern in text        -> refused
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from app import config
from app.pii.gate import EMAIL, PHONE, SSN

# Permanent PII quarantine — OPERATOR TlAB keep_quarantined (do not lift without HumanGate)
HARD_BLOCK_IDS = frozenset(
    {
        "ha-e9572b47baa503c3a27872fc",
        "ha-e9572b47",
        "ha-6a3868004d8868d9b08acd9e",
        "ha-6a3868004d8868d9b08acd9e-c0",
    }
)
HARD_BLOCK_BATCHES = frozenset(
    {
        "batch-002",  # PII quarantine lineage (gate wave2-2.3-batch-002-b08acd9e)
    }
)

# The threshold may be lowered via env but never raised above 0.80.
PII_CONFIDENCE_THRESHOLD = min(0.80, float(os.getenv("PII_CONFIDENCE_THRESHOLD", "0.80")))
MANIFEST_NAME = "hard-blocks.json"

_extra_ids: set[str] = set()
_extra_batches: set[str] = set()


def quarantine_dir() -> Path:
    return Path(config.CLEANER_QUARANTINE_DIR)


def seed_manifest() -> Path:
    """Write the hard-block manifest into the quarantine dir if it is missing."""
    qdir = quarantine_dir()
    qdir.mkdir(parents=True, exist_ok=True)
    path = qdir / MANIFEST_NAME
    if not path.exists():
        path.write_text(
            json.dumps(
                {
                    "source": "memory image app/quarantine.py (RW-1)",
                    "seeded_at": datetime.now(timezone.utc).isoformat(),
                    "blocked_ids": sorted(HARD_BLOCK_IDS),
                    "blocked_batches": sorted(HARD_BLOCK_BATCHES),
                    "note": "ids only; image constants remain authoritative even if this file is deleted",
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    return path


def _collect(obj: Any, ids: set[str], batches: set[str]) -> None:
    if isinstance(obj, dict):
        for k in ("id", "record_id", "chunk_id"):
            v = obj.get(k)
            if isinstance(v, str) and v:
                ids.add(v)
        for k in ("blocked_ids",):
            for v in obj.get(k) or []:
                if isinstance(v, str):
                    ids.add(v)
        for k in ("blocked_batches",):
            for v in obj.get(k) or []:
                if isinstance(v, str):
                    batches.add(v)
        b = obj.get("batch_id") or (obj.get("metadata") or {}).get("batch_id") or (obj.get("provenance") or {}).get("batch_id")
        if isinstance(b, str) and b:
            batches.add(b)


def load_quarantine_dir() -> dict[str, int]:
    """Union ids/batches from every *.json/*.jsonl in the quarantine dir."""
    ids: set[str] = set()
    batches: set[str] = set()
    qdir = quarantine_dir()
    if qdir.exists():
        for p in sorted(qdir.glob("*.json*")):
            try:
                if p.suffix == ".jsonl":
                    for line in p.read_text(encoding="utf-8").splitlines():
                        if line.strip():
                            _collect(json.loads(line), ids, batches)
                else:
                    _collect(json.loads(p.read_text(encoding="utf-8")), ids, batches)
            except Exception:  # noqa: BLE001 - a bad file must not unblock anything
                continue
    _extra_ids.clear()
    _extra_ids.update(ids)
    _extra_batches.clear()
    _extra_batches.update(batches)
    return {"extra_ids": len(ids), "extra_batches": len(batches)}


def blocked_ids() -> set[str]:
    return set(HARD_BLOCK_IDS) | _extra_ids


def blocked_batches() -> set[str]:
    return set(HARD_BLOCK_BATCHES) | _extra_batches


def is_blocked(ids: Iterable[str | None], batch_id: str | None = None) -> str | None:
    if batch_id and batch_id in blocked_batches():
        return f"batch:{batch_id}"
    bl = blocked_ids()
    for bid in ids:
        if not bid:
            continue
        if bid in bl:
            return bid
        if any(bid.startswith(b) or b in bid for b in bl if len(b) >= 11):
            return bid
    return None


def meta_blocked(meta: dict | None) -> str | None:
    meta = meta or {}
    return is_blocked(
        (meta.get("chunk_id"), meta.get("record_id")),
        batch_id=meta.get("batch_id"),
    )


def pii_refusal(text: str, metadata: dict | None, redaction_flag: bool) -> str | None:
    md = metadata or {}
    if md.get("quarantined"):
        return "quarantined"
    redacted = bool(redaction_flag or md.get("redaction_flag"))
    try:
        conf = float(md.get("pii_confidence") or 0.0)
    except (TypeError, ValueError):
        conf = 1.0
    if md.get("pii_flag") and not redacted and conf >= PII_CONFIDENCE_THRESHOLD:
        return "high_confidence_unredacted_pii"
    if not redacted:
        t = text or ""
        hits = [n for n, rx in (("email", EMAIL), ("phone", PHONE), ("ssn", SSN)) if rx.search(t)]
        if hits:
            return "pii_pattern:" + ",".join(hits)
    return None
