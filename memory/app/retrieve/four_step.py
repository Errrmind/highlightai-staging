"""Retrieval Steps 1–3 (CORE-BUILD-V1). Step 4 handed to Orchestrator."""
from __future__ import annotations

from typing import Any

from app.embed.local_embed import LocalEmbedder
from app.models import QueryHit, QueryRequest, QueryResponse
from app.store.memory_store import MemoryStore
from app.store.npy_index import NpyVectorIndex
from app.store.sqlite_graph import SqliteGraph


class FourStepRetriever:
    """1 embed → 2 filter/vector (.npy) → 3 SQLite expand. Step4 = orchestrator handoff."""

    STEPS = ("embed", "filter_metadata", "graph_expand", "orchestrator_step4")

    def __init__(
        self,
        store: MemoryStore | None = None,
        embedder: LocalEmbedder | None = None,
    ) -> None:
        self.store = store or MemoryStore()
        self.embedder = embedder or LocalEmbedder()

    def query(self, request: QueryRequest) -> QueryResponse:
        # Step 1 — embed
        qvec = self.embedder.embed([request.query])[0]

        # Step 2 — vector search + metadata filter
        index = NpyVectorIndex(request.project_id)
        candidates = index.search(
            qvec,
            top_k=max(request.top_k * 4, 16),
            filters={"project_id": request.project_id, "pii_flag": False},
        )
        # fallback to store scan if index empty (tests / fresh)
        if not candidates:
            for row in self.store.all_chunks(project_id=request.project_id):
                emb = row.get("embedding") or []
                if not emb:
                    continue
                # cosine
                import math

                def cos(a, b):
                    if not a or not b or len(a) != len(b):
                        return 0.0
                    dot = sum(x * y for x, y in zip(a, b))
                    na = math.sqrt(sum(x * x for x in a)) or 1.0
                    nb = math.sqrt(sum(y * y for y in b)) or 1.0
                    return dot / (na * nb)

                candidates.append({**row, "score": cos(qvec, emb)})
            candidates.sort(key=lambda r: r.get("score") or 0, reverse=True)
            candidates = candidates[: max(request.top_k * 4, 16)]

        # Step 3 — graph expand
        graph = SqliteGraph(request.project_id)
        seed_ids = []
        for c in candidates[: request.top_k]:
            if c.get("record_id"):
                seed_ids.append(c["record_id"])
            if c.get("chunk_id"):
                seed_ids.append(c["chunk_id"])
        expanded_ids = graph.expand(seed_ids, max_hops=1) if request.include_graph else []
        by_id = {c.get("chunk_id"): c for c in candidates}
        for eid in expanded_ids:
            for row in self.store.get_by_id(eid, project_id=request.project_id):
                cid = row.get("chunk_id")
                if cid and cid not in by_id:
                    row = dict(row)
                    row["score"] = float(row.get("score") or 0) + 0.05
                    candidates.append(row)
                    by_id[cid] = row

        candidates.sort(key=lambda r: r.get("score") or 0, reverse=True)

        # Assemble Step1–3 candidates for Orchestrator Step4
        hits: list[QueryHit] = []
        seen: set[str] = set()
        for row in candidates:
            rid = row.get("record_id") or row.get("chunk_id")
            if not rid or rid in seen:
                continue
            seen.add(rid)
            hits.append(
                QueryHit(
                    chunk_id=row.get("chunk_id") or "",
                    record_id=row.get("record_id") or "",
                    text=row.get("text") or "",
                    score=float(row.get("score") or 0),
                    step="graph",
                    metadata={
                        k: v
                        for k, v in row.items()
                        if k
                        not in {"text", "embedding", "score", "step", "chunk_id", "record_id"}
                    },
                )
            )
            if len(hits) >= request.top_k:
                break

        step4_handoff = {
            "for": "agent.orchestrator",
            "step": 4,
            "action": "assemble_context_bundle",
            "project_id": request.project_id,
            "query": request.query,
            "candidates": [
                {
                    "chunk_id": h.chunk_id,
                    "record_id": h.record_id,
                    "score": h.score,
                    "text": h.text,
                    "metadata": h.metadata,
                }
                for h in hits
            ],
        }

        return QueryResponse(
            query=request.query,
            project_id=request.project_id,
            hits=hits,
            steps=list(self.STEPS),
            mode="filesystem-local",
            step4_handoff=step4_handoff,
        )
