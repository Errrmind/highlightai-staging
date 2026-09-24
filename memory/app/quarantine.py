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

Batch refs are discovered at ANY nesting (metadata.batch_id,
metadata.provenance.batch_id, top-level provenance.batch_id, ...) and
normalized ('Batch_002', ' 002 ', 2 -> 'batch-002') on ingest AND read side.
Unparseable quarantine files fail closed (ingest 503, health 503).
"""
from __future__ import annotations

import json
import os
import re
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
# Fail-closed state: set when any quarantine file/line cannot be parsed.
_load_errors: list[str] = []

# Keys that may carry a batch reference, at any nesting depth (metadata,
# metadata.provenance, top-level provenance, source, lineage, ...).
BATCH_KEYS = frozenset({"batch_id", "batch", "batchid", "source_batch", "source_batch_id", "batch_name"})
ID_KEYS = ("id", "chunk_id", "record_id", "source_record_id", "parent_id")
_MAX_DEPTH = 6
_BATCH_RE = re.compile(r"^(?:batch)?[\s_\-:/]*0*(\d{1,6})$")


def normalize_batch(value: Any) -> str | None:
    """'batch-002', 'Batch_002', ' BATCH 2 ', '002', 2 -> 'batch-002'. Others: lowercased/stripped."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return f"batch-{value:03d}"
    if not isinstance(value, str):
        return None
    v = value.strip().lower()
    if not v:
        return None
    m = _BATCH_RE.match(v)
    if m:
        return f"batch-{int(m.group(1)):03d}"
    return v


def _is_batch_key(kl: str) -> bool:
    flat = kl.replace("_", "")
    return kl in BATCH_KEYS or flat in BATCH_KEYS or flat.endswith("batchid") or flat.endswith("batch")


def find_batches(obj: Any, depth: int = 0) -> set[str]:
    """Collect normalized batch refs from every plausible nesting of a record."""
    out: set[str] = set()
    if depth > _MAX_DEPTH:
        return out
    if isinstance(obj, dict):
        for k, v in obj.items():
            kl = str(k).lower().replace("-", "_")
            if _is_batch_key(kl):
                if isinstance(v, (list, tuple)):
                    for x in v:
                        n = normalize_batch(x)
                        if n:
                            out.add(n)
                else:
                    n = normalize_batch(v)
                    if n:
                        out.add(n)
            if isinstance(v, (dict, list, tuple)):
                out |= find_batches(v, depth + 1)
    elif isinstance(obj, (list, tuple)):
        for x in obj:
            out |= find_batches(x, depth + 1)
    return out


def find_ids(obj: Any, depth: int = 0) -> set[str]:
    out: set[str] = set()
    if depth > _MAX_DEPTH:
        return out
    if isinstance(obj, dict):
        for k in ID_KEYS:
            v = obj.get(k)
            if isinstance(v, str) and v:
                out.add(v)
        for v in obj.values():
            if isinstance(v, (dict, list, tuple)):
                out |= find_ids(v, depth + 1)
    elif isinstance(obj, (list, tuple)):
        for x in obj:
            out |= find_ids(x, depth + 1)
    return out


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
        ids |= find_ids(obj)
        for v in obj.get("blocked_ids") or []:
            if isinstance(v, str):
                ids.add(v)
        for v in obj.get("blocked_batches") or []:
            n = normalize_batch(v)
            if n:
                batches.add(n)
        batches |= find_batches(obj)


def load_quarantine_dir() -> dict[str, Any]:
    """Union ids/batches from every *.json/*.jsonl in the quarantine dir.

    FAIL-CLOSED: any unreadable file or unparseable line is recorded in
    _load_errors; while errors exist, ingest is refused (503) and health is 503.
    """
    ids: set[str] = set()
    batches: set[str] = set()
    errors: list[str] = []
    qdir = quarantine_dir()
    if qdir.exists():
        for p in sorted(qdir.glob("*.json*")):
            try:
                raw = p.read_text(encoding="utf-8")
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{p.name}: unreadable ({type(exc).__name__})")
                continue
            if p.suffix == ".jsonl":
                for n, line in enumerate(raw.splitlines(), 1):
                    if not line.strip():
                        continue
                    try:
                        _collect(json.loads(line), ids, batches)
                    except Exception as exc:  # noqa: BLE001
                        errors.append(f"{p.name}:{n}: unparseable ({type(exc).__name__})")
            else:
                try:
                    _collect(json.loads(raw), ids, batches)
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{p.name}: unparseable ({type(exc).__name__})")
    _extra_ids.clear()
    _extra_ids.update(ids)
    _extra_batches.clear()
    _extra_batches.update(batches)
    _load_errors.clear()
    _load_errors.extend(errors)
    return {"extra_ids": len(ids), "extra_batches": len(batches), "load_errors": len(errors)}


def load_errors() -> list[str]:
    return list(_load_errors)


def fail_closed() -> bool:
    return bool(_load_errors)


def blocked_ids() -> set[str]:
    return set(HARD_BLOCK_IDS) | _extra_ids


def blocked_batches() -> set[str]:
    return {normalize_batch(b) or b for b in HARD_BLOCK_BATCHES} | _extra_batches


def is_blocked(ids: Iterable[str | None], batch_id: Any = None, batches: Iterable[str] = ()) -> str | None:
    bb = blocked_batches()
    cand = set(batches)
    n = normalize_batch(batch_id)
    if n:
        cand.add(n)
    for b in sorted(cand):
        if b in bb:
            return f"batch:{b}"
    bl = blocked_ids()
    for bid in ids:
        if not bid:
            continue
        if bid in bl:
            return bid
        if any(bid.startswith(b) or b in bid for b in bl if len(b) >= 11):
            return bid
    return None


def record_blocked(record: Any) -> str | None:
    """Ingest-side check over the WHOLE record (top-level, metadata, provenance, nested)."""
    return is_blocked(sorted(find_ids(record)), batches=find_batches(record))


def meta_blocked(meta: dict | None) -> str | None:
    """Read-side check (query / chunk / export) over the stored metadata, any nesting."""
    meta = meta or {}
    return is_blocked(sorted(find_ids(meta)), batches=find_batches(meta))


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
