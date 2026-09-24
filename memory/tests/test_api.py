from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_endpoint():
    r = client.get("/memory/health")
    assert r.status_code == 200
    body = r.json()
    assert body["project_id"] == "highlightai-pending"
    assert "MiniLM" in body["embedding_model"] or "sentence-transformers" in body["embedding_model"]
    assert body["chunk_size"] == 512
    assert body["chunk_overlap"] == 64
    assert body["retention_days"] == 90
    assert "ingest_gates" in body


def test_root():
    r = client.get("/")
    assert r.status_code == 200
    assert r.json()["service"] == "highlightai-memory"


def test_ingest_blocked_without_artifacts():
    r = client.post("/memory/ingest", json={"project_id": "highlightai-pending", "dry_run": True})
    assert r.status_code == 200
    body = r.json()
    assert body["accepted"] is False
    assert body["blocked_by"]


def test_fixture_ingest_and_query(tmp_path, monkeypatch):
    from app import config
    from app.store.memory_store import MemoryStore
    import app.api.routes as routes

    store_root = tmp_path / "store"
    monkeypatch.setattr(config, "STORE_DIR", store_root)
    monkeypatch.setattr(config, "INDEX_DIR", tmp_path / "index")
    monkeypatch.setattr(config, "GRAPH_DIR", tmp_path / "graph")
    routes._store = MemoryStore(root=store_root, project_id="highlightai-pending")
    routes._pipeline = None
    routes._retriever = None

    rec = {
        "id": "rec-fx",
        "text": "Local vector index uses numpy npy files for HighlightAI memory retrieval.",
        "language": "en",
        "content_type": "text/plain",
        "entities": [],
        "provenance": {
            "source_url": "https://example.com/fx",
            "crawl_timestamp": "2026-09-19T00:00:00+00:00",
        },
        "metadata": {
            "project_id": "highlightai-pending",
            "pii_flag": False,
            "redaction_flag": False,
            "quarantined": False,
        },
    }
    r = client.post(
        "/memory/ingest",
        json={"project_id": "highlightai-pending", "fixture_mode": True, "records": [rec]},
    )
    assert r.status_code == 200
    assert r.json()["accepted"] is True
    assert r.json()["chunks_created"] >= 1

    q = client.post(
        "/memory/query",
        json={"query": "numpy npy memory retrieval", "project_id": "highlightai-pending", "top_k": 5},
    )
    assert q.status_code == 200
    body = q.json()
    assert body["steps"][:3] == ["embed", "filter_metadata", "graph_expand"]
    assert body["step4_handoff"]["for"] == "agent.orchestrator"
    assert len(body["hits"]) >= 1
