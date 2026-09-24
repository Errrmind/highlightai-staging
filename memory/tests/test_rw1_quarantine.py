"""RW-1 B1 regression: batch-002 hard-block in every nesting shape, ingest + read side.

Runs with the hash embedder (no model download); production_ready is forced so
the routes run, while /v1/health must still report 503 (hash backend).
"""
from __future__ import annotations

import json
import os

import pytest
from fastapi.testclient import TestClient

os.environ["FORCE_HASH_EMBED"] = "1"

PROJECT = "rw1-b1"

# (label, record) — every record carries batch-002 in a different place/spelling
BATCH002_SHAPES = [
    ("metadata.batch_id", {"metadata": {"batch_id": "batch-002"}}),
    ("metadata.provenance.batch_id", {"metadata": {"provenance": {"batch_id": "batch-002", "source_url": "https://example.com/b2"}}}),
    ("provenance.batch_id(top-level)", {"provenance": {"batch_id": "batch-002"}}),
    ("batch_id(top-level,'002')", {"batch_id": "002"}),
    ("metadata.provenance.batch_id(' BATCH-002 ')", {"metadata": {"provenance": {"batch_id": " BATCH-002 "}}}),
    ("metadata.provenance.batch_id('batch_002')", {"metadata": {"provenance": {"batch_id": "batch_002"}}}),
    ("metadata.provenance.batch_id(int 2)", {"metadata": {"provenance": {"batch_id": 2}}}),
    ("metadata.source.lineage.batch('Batch 2')", {"metadata": {"source": {"lineage": {"batch": "Batch 2"}}}}),
    ("extra top-level lineage.batchId", {"lineage": {"batchId": "batch-002"}}),
    ("metadata.provenance.batch_id(list)", {"metadata": {"provenance": {"batch_id": ["batch-001", "batch-002"]}}}),
]


@pytest.fixture()
def rt_client(tmp_path, monkeypatch):
    from app import config, quarantine
    from app.audit import AuditLogger
    from app.embedder import Embedder
    from app.graph_store import GraphStore
    from app.main import app
    from app.retrieval import RetrievalEngine
    from app.state import MemoryRuntime, set_runtime
    from app.vector_index import VectorIndex

    monkeypatch.setattr(config, "MEMORY_ARTIFACTS_DIR", tmp_path)
    monkeypatch.setattr(config, "EXPORT_DIR", tmp_path / "exports")
    monkeypatch.setattr(config, "CLEANER_QUARANTINE_DIR", tmp_path / "quarantine")
    quarantine.seed_manifest()
    quarantine.load_quarantine_dir()
    emb = Embedder(force_hash=True)
    idx = VectorIndex(tmp_path / "index", dim=emb.dim)
    graph = GraphStore(tmp_path / "graph.sqlite")
    ret = RetrievalEngine(emb, idx, graph, min_highlight_score=0.0)
    audit = AuditLogger(tmp_path / "audit.jsonl")
    rt = MemoryRuntime(emb, idx, graph, ret, audit, tmp_path, production_ready=True)
    set_runtime(rt)
    yield TestClient(app), rt, tmp_path
    graph.close()
    set_runtime(None)
    quarantine._load_errors.clear()


def _rec(i, extra):
    r = {"id": f"rw1-b1-{i}", "text": f"quarantined batch two record number {i} vector memory", "project_id": PROJECT, "highlight_score": 0.9}
    for k, v in extra.items():
        r[k] = v
    return r


@pytest.mark.parametrize("label,shape", BATCH002_SHAPES, ids=[s[0] for s in BATCH002_SHAPES])
def test_ingest_refuses_batch002_every_shape(rt_client, label, shape):
    client, rt, _ = rt_client
    r = client.post("/memory/ingest", json={"project_id": PROJECT, "records": [_rec(1, shape)]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["accepted"] == 0, (label, body)
    assert body["blocked_quarantine"] == ["batch:batch-002"], (label, body)
    assert rt.index.get("rw1-b1-1") is None


def test_control_batch003_accepted(rt_client):
    client, _, _ = rt_client
    r = client.post("/memory/ingest", json={"project_id": PROJECT, "records": [_rec(9, {"metadata": {"provenance": {"batch_id": "batch-003"}}})]})
    assert r.json()["accepted"] == 1


@pytest.mark.parametrize("label,shape", BATCH002_SHAPES, ids=[s[0] for s in BATCH002_SHAPES])
def test_read_side_hides_preexisting_batch002(rt_client, label, shape):
    """Simulate a batch-002 row already in the index (e.g. written by pre-fix code):
    query, chunk lookup and export must all refuse it."""
    client, rt, tmp = rt_client
    text = "legacy quarantined batch two memory row"
    meta = {"chunk_id": "legacy-1", "record_id": "legacy-1", "text": text, "project_id": PROJECT,
            "highlight_score": 0.9, "source_type": "documentation", "redaction_flag": False}
    # store the shape the way the ingest route stores it (metadata merged, top-level kept)
    stored = dict(meta)
    for k, v in shape.items():
        if k == "metadata":
            stored.update(v)
        elif k == "provenance":
            stored["top_provenance"] = v
        elif k == "batch_id":
            stored["top_batch_id"] = v
        else:
            stored[k] = v
    rt.index.add("legacy-1", rt.embedder.embed_one(text), stored)
    ok_text = "approved clear path memory row"
    rt.index.add("ok-1", rt.embedder.embed_one(ok_text), {**meta, "chunk_id": "ok-1", "record_id": "ok-1", "text": ok_text})

    q = client.post("/memory/query", json={"query": text, "project_id": PROJECT, "top_k": 5, "min_highlight_score": 0.0})
    ids = [h["chunk_id"] for h in q.json()["hits"]]
    assert "legacy-1" not in ids, (label, ids)
    assert "ok-1" in ids

    c = client.get("/memory/chunk/legacy-1")
    assert c.status_code == 403, (label, c.status_code)
    assert client.get("/memory/chunk/ok-1").status_code == 200

    e = client.get("/memory/export", params={"project_id": PROJECT, "format": "jsonl"})
    assert e.status_code == 200
    content = open(e.json()["path"], encoding="utf-8").read()
    assert "legacy-1" not in content and "ok-1" in content, label


def test_hard_block_ids_still_refused(rt_client):
    client, _, _ = rt_client
    recs = [
        {"id": "ha-e9572b47baa503c3a27872fc", "text": "x"},
        {"id": "ha-6a3868004d8868d9b08acd9e-c0", "text": "x"},
        {"id": "other", "record_id": "ha-6a3868004d8868d9b08acd9e", "text": "x"},
        {"id": "nested", "text": "x", "metadata": {"provenance": {"record_id": "ha-e9572b47baa503c3a27872fc"}}},
    ]
    b = client.post("/memory/ingest", json={"project_id": PROJECT, "records": recs}).json()
    assert b["accepted"] == 0 and len(b["blocked_quarantine"]) == 4


def test_metadata_cannot_overwrite_chunk_id(rt_client):
    client, rt, _ = rt_client
    r = client.post("/memory/ingest", json={"project_id": PROJECT, "records": [
        {"id": "real-id", "text": "spoof attempt", "project_id": PROJECT, "metadata": {"chunk_id": "spoofed", "project_id": "other"}}]}).json()
    assert r["accepted"] == 1
    m = rt.index.get("real-id")
    assert m["chunk_id"] == "real-id" and m["project_id"] == PROJECT


def test_unparseable_quarantine_file_fails_closed(rt_client):
    client, _, tmp = rt_client
    from app import quarantine

    (tmp / "quarantine" / "broken.jsonl").write_text('{"id": "x"}\n{not json\n', encoding="utf-8")
    st = quarantine.load_quarantine_dir()
    assert st["load_errors"] == 1 and quarantine.fail_closed()
    r = client.post("/memory/ingest", json={"project_id": PROJECT, "records": [_rec(5, {})]})
    assert r.status_code == 503
    assert client.get("/v1/health").status_code == 503


def test_health_503_on_hash_backend(rt_client):
    client, _, _ = rt_client
    r = client.get("/v1/health")
    assert r.status_code == 503
    assert r.json()["embedder_backend"] == "hash"


def test_export_sanitized(rt_client):
    client, _, _ = rt_client
    assert client.get("/memory/export", params={"project_id": "../../etc", "format": "jsonl"}).status_code == 400
    assert client.get("/memory/export", params={"project_id": PROJECT, "format": "sh"}).status_code == 400


def test_body_and_record_caps(rt_client):
    client, _, _ = rt_client
    big = "a" * (2 * 1024 * 1024 + 10)
    assert client.post("/memory/ingest", json={"project_id": PROJECT, "text": big}).status_code == 413
    many = [{"id": f"m{i}", "text": "t"} for i in range(300)]
    assert client.post("/memory/ingest", json={"project_id": PROJECT, "records": many}).status_code == 413


def test_deploy_mode_disables_mutations(rt_client, monkeypatch):
    client, _, _ = rt_client
    from app import routes

    monkeypatch.setattr(routes, "DEPLOY_MODE", True)
    assert client.delete("/memory/chunk/anything").status_code == 403
    assert client.post("/memory/link", json={"source_id": "a", "target_id": "b"}).status_code == 403
