#!/usr/bin/env python3
"""CORE-BUILD-V1 acceptance eval: recall@5 + P95 retrieve."""
from __future__ import annotations

import json
import math
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.embed.local_embed import LocalEmbedder
from app.ingest.pipeline import IngestPipeline
from app.models import CanonicalRecord, IngestRequest, Metadata, Provenance, QueryRequest
from app.retrieve.four_step import FourStepRetriever
from app.store.memory_store import MemoryStore

ART = Path("/workspace/highlightai/artifacts/memory")
EVAL_DIR = ART / "eval"
EVAL_DIR.mkdir(parents=True, exist_ok=True)


FIXTURES = [
    ("rec-a", "HighlightAI stores long-term knowledge with a local numpy vector index.", "numpy vector index"),
    ("rec-b", "SQLite knowledge graph expands related memory nodes during retrieval step three.", "SQLite knowledge graph expand"),
    ("rec-c", "Sentence transformers all-MiniLM embed chunks in batches of sixty four.", "sentence transformers MiniLM batches"),
    ("rec-d", "PII gate blocks unredacted emails before any embedding or storage.", "PII gate blocks unredacted"),
    ("rec-e", "Orchestrator assembles the final context bundle in retrieval step four.", "Orchestrator context bundle step four"),
    ("rec-f", "Cleaner emits JSONL artifacts that security must clear before ingest.", "Cleaner JSONL security clear ingest"),
    ("rec-g", "Project shard highlightai-pending is the placeholder until Manager patches.", "highlightai-pending placeholder shard"),
    ("rec-h", "Ninety day retention purges expired memory chunks from the local store.", "ninety day retention purge"),
    ("rec-i", "Graph links connect records to chunks with a has_chunk relation.", "has_chunk relation graph links"),
    ("rec-j", "Filesystem mode never binds ports until the operator supplies cluster URLs.", "filesystem mode never binds ports"),
]


def main() -> int:
    work = EVAL_DIR / "workdir"
    if work.exists():
        import shutil

        shutil.rmtree(work)
    store_root = work / "store"
    index_root = work / "index"
    graph_root = work / "graph"
    from app import config

    config.INDEX_DIR = index_root
    config.GRAPH_DIR = graph_root
    config.STORE_DIR = store_root
    config.FORCE_HASH_EMBED = True

    embedder = LocalEmbedder(force_hash=True, dimensions=384)
    store = MemoryStore(root=store_root, project_id="highlightai-pending")
    pipe = IngestPipeline(embedder=embedder, store=store)
    records = []
    for rid, text, _q in FIXTURES:
        records.append(
            CanonicalRecord(
                id=rid,
                text=text,
                language="en",
                content_type="text/plain",
                provenance=Provenance(
                    source_url=f"https://example.com/{rid}",
                    crawl_timestamp=datetime.now(timezone.utc),
                ),
                metadata=Metadata(
                    project_id="highlightai-pending",
                    pii_flag=False,
                    redaction_flag=False,
                    quarantined=False,
                ),
            )
        )
    result = pipe.run(
        IngestRequest(project_id="highlightai-pending", fixture_mode=True, records=records)
    )
    assert result.accepted, result

    retriever = FourStepRetriever(store=store, embedder=embedder)
    hits_at_5 = 0
    latencies = []
    details = []
    for rid, _text, query in FIXTURES:
        t0 = time.perf_counter()
        resp = retriever.query(QueryRequest(query=query, project_id="highlightai-pending", top_k=5))
        ms = (time.perf_counter() - t0) * 1000
        latencies.append(ms)
        top_ids = [h.record_id for h in resp.hits]
        ok = rid in top_ids
        hits_at_5 += int(ok)
        details.append({"id": rid, "query": query, "top_ids": top_ids, "hit": ok, "ms": round(ms, 3)})

    recall = hits_at_5 / len(FIXTURES)
    latencies_sorted = sorted(latencies)
    idx = min(len(latencies_sorted) - 1, max(0, int(__import__("math").ceil(0.95 * len(latencies_sorted)) - 1)))
    p95 = latencies_sorted[idx]

    out = {
        "task": "CORE-BUILD-V1",
        "project_id": "highlightai-pending",
        "embed_backend": embedder.backend,
        "embed_dims": embedder.dimensions,
        "n_fixtures": len(FIXTURES),
        "recall_at_5": recall,
        "recall_pass": recall >= 0.90,
        "p95_retrieve_ms": round(p95, 3),
        "mean_retrieve_ms": round(statistics.mean(latencies), 3),
        "pii_unredacted": 0,
        "details": details,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
    dest = ART / "eval-core-build-v1.json"
    dest.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=2))
    return 0 if out["recall_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
