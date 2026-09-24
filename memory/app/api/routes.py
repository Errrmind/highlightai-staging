"""Memory HTTP routes — mounted under /memory/*."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app import config
from app.ingest.contract import IngestContract
from app.ingest.pipeline import IngestPipeline
from app.models import (
    DeleteRequest,
    ExportRequest,
    GetByIdRequest,
    HealthResponse,
    IngestRequest,
    IngestResult,
    LinkRequest,
    QueryRequest,
    QueryResponse,
)
from app.retrieve.four_step import FourStepRetriever
from app.embed.local_embed import LocalEmbedder
from app.store.memory_store import MemoryStore

router = APIRouter(prefix="/memory", tags=["memory"])

_store: MemoryStore | None = None
_pipeline: IngestPipeline | None = None
_retriever: FourStepRetriever | None = None
_contract = IngestContract()


def _get_store() -> MemoryStore:
    global _store
    if _store is None:
        _store = MemoryStore()
    return _store


def _get_pipeline() -> IngestPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = IngestPipeline(store=_get_store())
    return _pipeline


def _get_retriever() -> FourStepRetriever:
    global _retriever
    if _retriever is None:
        _retriever = FourStepRetriever(store=_get_store())
    return _retriever


@router.post("/ingest", response_model=IngestResult)
def ingest(body: IngestRequest) -> IngestResult:
    """Ingest cleaner JSONL only when security gates pass."""
    return _get_pipeline().run(body)


@router.post("/query", response_model=QueryResponse)
def query(body: QueryRequest) -> QueryResponse:
    return _get_retriever().query(body)


@router.post("/get-by-id")
def get_by_id(body: GetByIdRequest) -> dict:
    rows = _get_store().get_by_id(body.id, project_id=body.project_id)
    if not rows:
        raise HTTPException(status_code=404, detail="not_found")
    # strip embeddings from response
    cleaned = []
    for r in rows:
        r = dict(r)
        r.pop("embedding", None)
        cleaned.append(r)
    return {"id": body.id, "project_id": body.project_id, "chunks": cleaned}


@router.post("/link")
def link(body: LinkRequest) -> dict:
    return _get_store().link(
        body.source_id,
        body.target_id,
        body.relation,
        body.project_id,
        body.properties,
    )


@router.post("/delete")
def delete(body: DeleteRequest) -> dict:
    removed = _get_store().delete(body.id, project_id=body.project_id, hard=body.hard)
    return {"id": body.id, "removed": removed, "hard": body.hard}


@router.post("/export")
def export(body: ExportRequest) -> dict:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = config.EXPORT_DIR / f"export-{body.project_id}-{ts}.{body.format}"
    path = _get_store().export(body.project_id, dest, fmt=body.format)
    return {"path": str(path), "project_id": body.project_id, "format": body.format}


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    gates = _contract.evaluate()
    status = "ok" if config.MEMORY_MODE == "filesystem" else "degraded"
    detail = (
        "CORE-BUILD-V1 local mode: MiniLM/hash embed + npy index + SQLite graph; Step4→Orchestrator"
    )
    if config.stores_configured():
        detail = "stores configured; still placeholder project_id" if (
            config.PROJECT_ID == "highlightai-pending"
        ) else "cluster stores configured"
        status = "ok"
    return HealthResponse(
        status=status,
        mode=config.MEMORY_MODE,
        project_id=config.PROJECT_ID,
        stores_configured=config.stores_configured(),
        ingest_gates={
            "cleaner_ready": gates.cleaner_ready,
            "security_ready": gates.security_ready,
        },
        embedding_model=config.EMBEDDING_MODEL,
        chunk_size=config.CHUNK_SIZE,
        chunk_overlap=config.CHUNK_OVERLAP,
        retention_days=config.RETENTION_DAYS,
        detail=detail,
    )
