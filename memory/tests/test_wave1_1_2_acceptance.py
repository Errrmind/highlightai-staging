"""WAVE1-1.2 — 9 acceptance tests for numpy+sqlite Memory upgrade."""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

# Force hash embedder for fast/deterministic CI (dim still 384)
import os

os.environ["FORCE_HASH_EMBED"] = "1"
os.environ["MEMORY_PORT"] = "8092"


@pytest.fixture()
def tmp_runtime(tmp_path, monkeypatch):
    from app import config
    from app.audit import AuditLogger
    from app.embedder import Embedder
    from app.graph_store import GraphStore
    from app.main import app
    from app.retrieval import RetrievalEngine
    from app.state import MemoryRuntime, set_runtime
    from app.vector_index import VectorIndex

    monkeypatch.setattr(config, "MEMORY_ARTIFACTS_DIR", tmp_path)
    monkeypatch.setattr(config, "EXPORT_DIR", tmp_path / "exports")
    monkeypatch.setattr(config, "PROJECT_ID", "highlightai-pending")
    (tmp_path / "exports").mkdir(parents=True, exist_ok=True)

    emb = Embedder(force_hash=True)
    idx = VectorIndex(tmp_path / "index", dim=emb.dim)
    graph = GraphStore(tmp_path / "graph.sqlite")
    ret = RetrievalEngine(emb, idx, graph, min_highlight_score=0.25)
    audit = AuditLogger(tmp_path / "audit.jsonl")
    rt = MemoryRuntime(emb, idx, graph, ret, audit, tmp_path, production_ready=True)
    set_runtime(rt)
    client = TestClient(app)
    yield client, rt
    idx.save()
    graph.close()
    set_runtime(None)


def test_01_vector_add_search_delete_rebuild(tmp_runtime):
    _, rt = tmp_runtime
    v = rt.embedder.embed_one("numpy memmap cosine search")
    rt.index.add(
        "c1",
        v,
        {
            "project_id": "p1",
            "text": "numpy memmap cosine search",
            "highlight_score": 0.9,
            "source_type": "documentation",
            "redaction_flag": False,
            "record_id": "r1",
        },
    )
    hits = rt.index.search(v, top_k=5, project_id="p1", min_highlight_score=0.25)
    assert hits and hits[0]["chunk_id"] == "c1"
    assert rt.index.delete("c1") is True
    assert len(rt.index) == 0
    # soft-delete rebuild threshold
    for i in range(10):
        vv = rt.embedder.embed_one(f"doc {i}")
        rt.index.add(
            f"x{i}",
            vv,
            {
                "project_id": "p1",
                "text": f"doc {i}",
                "highlight_score": 0.8,
                "source_type": "documentation",
                "redaction_flag": False,
            },
        )
    for i in range(4):  # 4/10 = 40% > 30%
        rt.index.delete(f"x{i}")
    assert len(rt.index) == 6
    assert rt.index.deleted_ratio <= 0.30 + 1e-9  # rebuilt


def test_02_graph_bfs_expand(tmp_runtime):
    _, rt = tmp_runtime
    g = rt.graph
    g.add_node("a", "record", project_id="p1")
    g.add_node("b", "chunk", project_id="p1")
    g.add_node("c", "chunk", project_id="p1")
    g.add_edge("a", "b", "has_chunk", project_id="p1")
    g.add_edge("b", "c", "related_to", project_id="p1")
    edges = g.expand(["a"], max_depth=2, limit=50)
    assert len(edges) >= 2
    assert g.count()["nodes"] >= 3


def test_03_embedder_dim_l2(tmp_runtime):
    _, rt = tmp_runtime
    v = rt.embedder.embed_one("hello world")
    assert v.shape == (384,)
    assert abs(float(np.linalg.norm(v)) - 1.0) < 1e-3
    batch = rt.embedder.embed_batch(["a", "b"])
    assert batch.shape == (2, 384)


def test_04_retrieval_confidence_and_min_highlight(tmp_runtime):
    _, rt = tmp_runtime
    from app.retrieval import RetrievalEngine

    assert abs(RetrievalEngine.confidence(1.0, 0.0) - 0.7) < 1e-9
    assert abs(RetrievalEngine.confidence(0.0, 1.0) - 0.3) < 1e-9
    assert rt.retrieval.min_highlight_score == 0.25
    low = rt.embedder.embed_one("alpha topic unique")
    high = rt.embedder.embed_one("beta topic unique")
    rt.index.add(
        "low",
        low,
        {
            "project_id": "p1",
            "text": "alpha topic unique",
            "highlight_score": 0.1,
            "source_type": "documentation",
            "redaction_flag": False,
        },
    )
    rt.index.add(
        "high",
        high,
        {
            "project_id": "p1",
            "text": "beta topic unique",
            "highlight_score": 0.9,
            "source_type": "documentation",
            "redaction_flag": False,
        },
    )
    out = rt.retrieval.query("beta topic unique", project_id="p1", top_k=5)
    ids = [h["chunk_id"] for h in out["hits"]]
    assert "high" in ids
    assert "low" not in ids  # filtered by min_highlight_score 0.25
    for h in out["hits"]:
        expected = h["similarity"] * 0.7 + h["highlight_score"] * 0.3
        assert abs(h["confidence"] - expected) < 1e-6


def test_05_health_production_ready(tmp_runtime):
    client, _ = tmp_runtime
    r = client.get("/memory/health")
    assert r.status_code == 200
    body = r.json()
    assert body.get("production_ready") is True
    assert body.get("status") == "ok"


def test_06_ingest_query_roundtrip(tmp_runtime):
    client, _ = tmp_runtime
    r = client.post(
        "/memory/ingest",
        json={
            "project_id": "p1",
            "records": [
                {
                    "id": "chk-rt-1",
                    "text": "HighlightAI local vector memory uses cosine similarity",
                    "project_id": "p1",
                    "highlight_score": 0.85,
                    "source_type": "documentation",
                }
            ],
        },
    )
    assert r.status_code == 200
    assert r.json()["accepted"] >= 1
    q = client.post(
        "/memory/query",
        json={"query": "cosine similarity vector memory", "project_id": "p1", "top_k": 5},
    )
    assert q.status_code == 200
    hits = q.json()["hits"]
    assert hits
    assert any("chk-rt-1" == h["chunk_id"] for h in hits)


def test_07_link_edges(tmp_runtime):
    client, rt = tmp_runtime
    r = client.post(
        "/memory/link",
        json={
            "source_id": "n1",
            "target_id": "n2",
            "relation": "related_to",
            "project_id": "p1",
        },
    )
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    edges = rt.graph.get_edges_from("n1")
    assert edges and edges[0]["target_id"] == "n2"


def test_08_soft_delete_rebuild_threshold(tmp_runtime):
    _, rt = tmp_runtime
    for i in range(5):
        rt.index.add(
            f"d{i}",
            rt.embedder.embed_one(f"item {i}"),
            {
                "project_id": "p1",
                "text": f"item {i}",
                "highlight_score": 0.5,
                "source_type": "documentation",
                "redaction_flag": False,
            },
        )
    # delete 2/5 = 40% triggers rebuild inside delete()
    rt.index.delete("d0")
    rt.index.delete("d1")
    assert len(rt.index) == 3
    assert all(not d for d in rt.index._deleted)


def test_09_stats_endpoint(tmp_runtime):
    client, rt = tmp_runtime
    rt.index.add(
        "s1",
        rt.embedder.embed_one("stats"),
        {
            "project_id": "p1",
            "text": "stats",
            "highlight_score": 0.5,
            "source_type": "documentation",
            "redaction_flag": False,
        },
    )
    r = client.get("/memory/stats", params={"project_id": "p1"})
    assert r.status_code == 200
    body = r.json()
    assert body["chunk_count"] >= 1
    assert body["production_ready"] is True
    assert "graph" in body
