"""4-step retrieval engine — WAVE1-1.2."""
from __future__ import annotations

from typing import Any

import numpy as np

from app.embedder import Embedder
from app.graph_store import GraphStore
from app.vector_index import VectorIndex

DEFAULT_MIN_HIGHLIGHT = 0.25


class RetrievalEngine:
    """1 embed → 2 metadata+vector filter → 3 graph BFS → 4 context bundle."""

    STEPS = ("embed", "filter_metadata", "graph_expand", "assemble")

    def __init__(
        self,
        embedder: Embedder,
        index: VectorIndex,
        graph: GraphStore,
        min_highlight_score: float = DEFAULT_MIN_HIGHLIGHT,
    ) -> None:
        self.embedder = embedder
        self.index = index
        self.graph = graph
        self.min_highlight_score = float(min_highlight_score)

    @staticmethod
    def confidence(sim: float, highlight: float) -> float:
        return float(sim) * 0.7 + float(highlight) * 0.3

    def query(
        self,
        query: str,
        *,
        project_id: str | None = None,
        top_k: int = 8,
        min_highlight_score: float | None = None,
        source_type: str | None = None,
        expand: bool = True,
    ) -> dict[str, Any]:
        min_hs = self.min_highlight_score if min_highlight_score is None else float(min_highlight_score)

        # Step 1 — embed
        qvec = self.embedder.embed_one(query)

        # Step 2 — vector search + metadata filters
        candidates = self.index.search(
            qvec,
            top_k=max(top_k * 4, 16),
            project_id=project_id,
            min_highlight_score=min_hs,
            source_type=source_type,
            exclude_redacted=True,
        )

        # Step 3 — graph expand
        expanded_edges: list[dict[str, Any]] = []
        if expand and candidates:
            seeds = []
            for c in candidates[:top_k]:
                seeds.append(c["chunk_id"])
                rid = c.get("record_id")
                if rid:
                    seeds.append(str(rid))
            expanded_edges = self.graph.expand(seeds, max_depth=2, limit=50)
            # pull neighbor chunk nodes into candidate pool lightly
            for e in expanded_edges:
                for nid in (e["source_id"], e["target_id"]):
                    meta = self.index.get(nid)
                    if meta and not any(c["chunk_id"] == nid for c in candidates):
                        candidates.append(
                            {
                                "chunk_id": nid,
                                "score": 0.05,
                                "similarity": 0.05,
                                "metadata": meta,
                                "text": meta.get("text") or "",
                                "highlight_score": float(meta.get("highlight_score") or 0.0),
                                "record_id": meta.get("record_id") or nid,
                                "project_id": meta.get("project_id"),
                            }
                        )

        # Step 4 — assemble with confidence
        bundle: list[dict[str, Any]] = []
        seen: set[str] = set()
        for c in sorted(candidates, key=lambda r: r.get("similarity") or r.get("score") or 0, reverse=True):
            cid = c["chunk_id"]
            if cid in seen:
                continue
            seen.add(cid)
            sim = float(c.get("similarity") or c.get("score") or 0.0)
            hs = float(c.get("highlight_score") or 0.0)
            conf = self.confidence(sim, hs)
            bundle.append(
                {
                    "chunk_id": cid,
                    "record_id": c.get("record_id") or cid,
                    "text": c.get("text") or "",
                    "similarity": sim,
                    "highlight_score": hs,
                    "confidence": conf,
                    "score": conf,
                    "metadata": c.get("metadata") or {},
                    "project_id": c.get("project_id"),
                }
            )
            if len(bundle) >= top_k:
                break

        return {
            "query": query,
            "project_id": project_id,
            "steps": list(self.STEPS),
            "hits": bundle,
            "graph_edges": expanded_edges[:50],
            "min_highlight_score": min_hs,
        }
