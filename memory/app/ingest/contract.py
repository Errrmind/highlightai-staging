"""Ingest contract — cleaner out/ + security signals required before any write.

DO NOT ingest until both gates pass. Quarantined cleaner JSONL is never read.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from app import config


@dataclass
class GateStatus:
    cleaner_ready: bool
    security_ready: bool
    cleaner_files: list[str] = field(default_factory=list)
    security_files: list[str] = field(default_factory=list)
    blocked_by: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.cleaner_ready and self.security_ready and not self.blocked_by


class IngestContract:
    """Filesystem gates per Manager paths.md + operator-gaps.md."""

    def __init__(
        self,
        cleaner_out: Path | None = None,
        cleaner_quarantine: Path | None = None,
        security_dir: Path | None = None,
    ) -> None:
        self.cleaner_out = cleaner_out or config.CLEANER_OUT_DIR
        self.cleaner_quarantine = cleaner_quarantine or config.CLEANER_QUARANTINE_DIR
        self.security_dir = security_dir or config.SECURITY_DIR

    def evaluate(self) -> GateStatus:
        blocked: list[str] = []
        cleaner_files = self._list_jsonl(self.cleaner_out)
        # Explicitly ignore quarantine — never ingest from there.
        security_files = self._list_security(self.security_dir)

        cleaner_ready = len(cleaner_files) > 0
        security_ready = len(security_files) > 0

        if not cleaner_ready:
            blocked.append("missing_cleaner_jsonl:artifacts/cleaner/out/")
        if not security_ready:
            blocked.append("missing_security_signals:artifacts/security/")

        return GateStatus(
            cleaner_ready=cleaner_ready,
            security_ready=security_ready,
            cleaner_files=[str(p) for p in cleaner_files],
            security_files=[str(p) for p in security_files],
            blocked_by=blocked,
        )

    def _list_jsonl(self, directory: Path) -> list[Path]:
        if not directory.exists():
            return []
        return sorted(p for p in directory.glob("*.jsonl") if p.is_file())

    def _list_security(self, directory: Path) -> list[Path]:
        if not directory.exists():
            return []
        files: list[Path] = []
        for pattern in ("*.sarif", "*.sarif.json", "*signal*.json", "*verified*.json"):
            files.extend(p for p in directory.glob(pattern) if p.is_file())
        # de-dupe preserve order
        seen: set[Path] = set()
        out: list[Path] = []
        for p in sorted(files):
            if p not in seen:
                seen.add(p)
                out.append(p)
        return out


CONTRACT_DOC = """
# Memory ingest contract

Ingest is blocked until ALL of the following are true:

1. Non-quarantined cleaner JSONL exists under `artifacts/cleaner/out/*.jsonl`
   - Never read `artifacts/cleaner/quarantine/`
2. Security-verified SARIF or signal files exist under `artifacts/security/`
   - Accepted names: `*.sarif`, `*.sarif.json`, `*signal*.json`, `*verified*.json`
3. `project_id` is the Manager placeholder `highlightai-pending` until a real shard is assigned
4. Records validate against `schemas/canonical-v2.1.json`
5. PII gate allows the record (high-confidence unredacted PII is rejected)
6. Qdrant/Neo4j URLs are optional for dry-run/filesystem staging; live upsert waits on operator-gaps.md

Schema: each JSONL line must be a Canonical Record v2.1 with required
`id`, `text`, `provenance`, `metadata` (including `project_id`, `pii_flag`, `redaction_flag`).
"""
