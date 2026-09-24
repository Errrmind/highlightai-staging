"""Ingest pipeline: gate → validate → PII → chunk → local embed → npy/sqlite store."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from app import config
from app.embed.local_embed import LocalEmbedder
from app.ingest.contract import IngestContract
from app.models import CanonicalRecord, Chunk, IngestRequest, IngestResult
from app.pii.gate import PiiGate
from app.retention.policy import RetentionPolicy
from app.store.memory_store import MemoryStore


def chunk_text(
    text: str,
    chunk_size: int = config.CHUNK_SIZE,
    overlap: int = config.CHUNK_OVERLAP,
) -> list[tuple[int, int, str]]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be >= 0 and < chunk_size")
    if not text:
        return []
    pieces: list[tuple[int, int, str]] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + chunk_size, n)
        pieces.append((start, end, text[start:end]))
        if end >= n:
            break
        start = end - overlap
    return pieces


class IngestPipeline:
    def __init__(
        self,
        contract: IngestContract | None = None,
        pii: PiiGate | None = None,
        retention: RetentionPolicy | None = None,
        embedder: LocalEmbedder | None = None,
        store: MemoryStore | None = None,
    ) -> None:
        self.contract = contract or IngestContract()
        self.pii = pii or PiiGate()
        self.retention = retention or RetentionPolicy()
        self.embedder = embedder or LocalEmbedder()
        self.store = store or MemoryStore()

    def run(self, request: IngestRequest | None = None) -> IngestResult:
        request = request or IngestRequest()
        if request.project_id != config.PROJECT_ID and request.project_id != "highlightai-pending":
            return IngestResult(
                accepted=False,
                reason="project_id_not_allowed",
                blocked_by=[f"unknown_project_id:{request.project_id}"],
            )

        if not request.fixture_mode:
            gates = self.contract.evaluate()
            if not gates.ok:
                return IngestResult(
                    accepted=False,
                    reason="ingest_gates_failed",
                    blocked_by=gates.blocked_by,
                )

        records_seen = 0
        chunks_created = 0
        skipped_quarantined = 0
        skipped_pii = 0
        all_chunks: list[Chunk] = []

        records: list[CanonicalRecord] = list(request.records or [])
        if not records:
            if request.source_jsonl:
                path = Path(request.source_jsonl)
                records.extend(self._iter_records(path))
            elif not request.fixture_mode:
                for path in sorted(self.contract.cleaner_out.glob("*.jsonl")):
                    records.extend(self._iter_records(path))

        for record in records:
            records_seen += 1
            if record.metadata.quarantined:
                skipped_quarantined += 1
                continue
            decision = self.pii.evaluate(record)
            if not decision.allow:
                skipped_pii += 1
                continue
            text = record.text
            if decision.redaction_flag:
                text = self.pii.redact_text(text)
            created = datetime.now(timezone.utc)
            for idx, (start, end, piece) in enumerate(chunk_text(text)):
                all_chunks.append(
                    Chunk(
                        chunk_id=f"{record.id}::c{idx}",
                        record_id=record.id,
                        text=piece,
                        index=idx,
                        start=start,
                        end=end,
                        project_id=request.project_id,
                        created_at=created,
                        expires_at=self.retention.expires_at(created),
                        pii_flag=decision.pii_flag,
                        metadata={
                            "provenance": record.provenance.model_dump(mode="json"),
                            "language": record.language,
                            "content_type": record.content_type,
                        },
                    )
                )

        if request.dry_run:
            return IngestResult(
                accepted=True,
                reason="dry_run",
                records_seen=records_seen,
                chunks_created=len(all_chunks),
                skipped_quarantined=skipped_quarantined,
                skipped_pii=skipped_pii,
            )

        if all_chunks:
            vectors = self.embedder.embed([c.text for c in all_chunks])
            for chunk, vec in zip(all_chunks, vectors):
                chunk.embedding = vec
            self.store.upsert_chunks(all_chunks)
            chunks_created = len(all_chunks)

        return IngestResult(
            accepted=True,
            reason="ok" if chunks_created else "ok_empty",
            records_seen=records_seen,
            chunks_created=chunks_created,
            skipped_quarantined=skipped_quarantined,
            skipped_pii=skipped_pii,
        )

    def _iter_records(self, path: Path) -> Iterator[CanonicalRecord]:
        with path.open("r", encoding="utf-8") as fh:
            for line_no, line in enumerate(fh, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    raw = json.loads(line)
                    yield CanonicalRecord.model_validate(raw)
                except Exception as exc:  # noqa: BLE001
                    _ = (line_no, exc)
                    continue
