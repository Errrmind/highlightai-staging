from __future__ import annotations

from datetime import datetime, timezone

from app.embed.local_embed import LocalEmbedder
from app.models import Chunk, QueryRequest
from app.retrieve.four_step import FourStepRetriever
from app.retention.policy import RetentionPolicy
from app.store.memory_store import MemoryStore


def test_four_step_query(tmp_store: MemoryStore, stub_embedder: LocalEmbedder, tmp_path, monkeypatch):
    from app import config

    monkeypatch.setattr(config, "INDEX_DIR", tmp_path / "index")
    monkeypatch.setattr(config, "GRAPH_DIR", tmp_path / "graph")
    store = MemoryStore(root=tmp_path / "store2", project_id="highlightai-pending")
    retention = RetentionPolicy()
    created = datetime.now(timezone.utc)
    text = "vector databases help memory retrieval for highlightai"
    emb = stub_embedder.embed([text])[0]
    store.upsert_chunks(
        [
            Chunk(
                chunk_id="rec-1::c0",
                record_id="rec-1",
                text=text,
                index=0,
                start=0,
                end=len(text),
                project_id="highlightai-pending",
                created_at=created,
                expires_at=retention.expires_at(created),
                embedding=emb,
            )
        ]
    )
    retriever = FourStepRetriever(store=store, embedder=stub_embedder)
    resp = retriever.query(
        QueryRequest(query="memory retrieval", project_id="highlightai-pending", top_k=3)
    )
    assert resp.steps == ["embed", "filter_metadata", "graph_expand", "orchestrator_step4"]
    assert len(resp.hits) >= 1
    assert resp.hits[0].record_id == "rec-1"
    assert resp.step4_handoff["step"] == 4
