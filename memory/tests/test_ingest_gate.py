from __future__ import annotations

from pathlib import Path

from app.ingest.contract import IngestContract
from app.ingest.pipeline import IngestPipeline, chunk_text
from app.models import IngestRequest
from app.store.memory_store import MemoryStore


def test_chunk_512_overlap_64():
    text = "x" * 1200
    pieces = chunk_text(text, chunk_size=512, overlap=64)
    assert pieces[0] == (0, 512, "x" * 512)
    assert pieces[1][0] == 512 - 64
    assert all(len(p[2]) <= 512 for p in pieces)


def test_ingest_blocked_without_gates(tmp_path: Path, tmp_store: MemoryStore):
    contract = IngestContract(
        cleaner_out=tmp_path / "missing_out",
        cleaner_quarantine=tmp_path / "q",
        security_dir=tmp_path / "missing_sec",
    )
    pipe = IngestPipeline(contract=contract, store=tmp_store)
    result = pipe.run(IngestRequest(dry_run=True))
    assert result.accepted is False
    assert any("cleaner" in b for b in result.blocked_by)
    assert any("security" in b for b in result.blocked_by)


def test_ingest_dry_run_when_gated(gated_dirs, tmp_store: MemoryStore):
    contract = IngestContract(
        cleaner_out=gated_dirs["cleaner"],
        cleaner_quarantine=gated_dirs["quarantine"],
        security_dir=gated_dirs["security"],
    )
    pipe = IngestPipeline(contract=contract, store=tmp_store)
    result = pipe.run(IngestRequest(dry_run=True))
    assert result.accepted is True
    assert result.records_seen == 1
    assert result.chunks_created >= 1


def test_refuse_unknown_project_id(gated_dirs, tmp_store: MemoryStore):
    contract = IngestContract(
        cleaner_out=gated_dirs["cleaner"],
        cleaner_quarantine=gated_dirs["quarantine"],
        security_dir=gated_dirs["security"],
    )
    pipe = IngestPipeline(contract=contract, store=tmp_store)
    result = pipe.run(IngestRequest(project_id="prod-shard-invented", dry_run=True))
    assert result.accepted is False
    assert result.reason == "project_id_not_allowed"
