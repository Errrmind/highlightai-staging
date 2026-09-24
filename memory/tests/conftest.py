from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))

from app.embed.local_embed import LocalEmbedder  # noqa: E402
from app.store.memory_store import MemoryStore  # noqa: E402


@pytest.fixture()
def tmp_store(tmp_path: Path) -> MemoryStore:
    return MemoryStore(root=tmp_path / "store", project_id="highlightai-pending")


@pytest.fixture()
def stub_embedder() -> LocalEmbedder:
    return LocalEmbedder(force_hash=True, dimensions=64)


@pytest.fixture()
def sample_record() -> dict:
    return {
        "id": "rec-1",
        "text": "HighlightAI memory stores cleaned documents for retrieval.",
        "language": "en",
        "content_type": "text/plain",
        "entities": [],
        "provenance": {
            "source_url": "https://example.com/doc",
            "crawl_timestamp": "2026-09-19T00:00:00+00:00",
            "license_header": None,
            "batch_id": "b1",
        },
        "metadata": {
            "project_id": "highlightai-pending",
            "chat_id": None,
            "pii_flag": False,
            "pii_confidence": 0.0,
            "redaction_flag": False,
            "quarantined": False,
        },
    }


@pytest.fixture()
def gated_dirs(tmp_path: Path, sample_record: dict) -> dict:
    cleaner = tmp_path / "cleaner" / "out"
    quarantine = tmp_path / "cleaner" / "quarantine"
    security = tmp_path / "security"
    cleaner.mkdir(parents=True)
    quarantine.mkdir(parents=True)
    security.mkdir(parents=True)
    (cleaner / "batch.jsonl").write_text(json.dumps(sample_record) + "\n", encoding="utf-8")
    (security / "scan.sarif").write_text('{"version":"2.1.0","runs":[]}\n', encoding="utf-8")
    return {"cleaner": cleaner, "quarantine": quarantine, "security": security}
