"""Shared runtime objects for Memory WAVE1-1.2."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.audit import AuditLogger
from app.embedder import Embedder
from app.graph_store import GraphStore
from app.retrieval import RetrievalEngine
from app.vector_index import VectorIndex


@dataclass
class MemoryRuntime:
    embedder: Embedder
    index: VectorIndex
    graph: GraphStore
    retrieval: RetrievalEngine
    audit: AuditLogger
    data_dir: Path
    production_ready: bool = True


_RUNTIME: Optional[MemoryRuntime] = None


def get_runtime() -> MemoryRuntime:
    if _RUNTIME is None:
        raise RuntimeError("memory runtime not started")
    return _RUNTIME


def set_runtime(rt: MemoryRuntime | None) -> None:
    global _RUNTIME
    _RUNTIME = rt
