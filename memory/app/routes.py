"""WAVE1-1.2 HTTP routes — exact contract under /memory/*."""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from app import config
from app.embedder import DIM
from app.state import get_runtime


# WAVE2-2.3 / RW-1: hard-blocks + PII gate live in app/quarantine.py (ship in image)
from app import quarantine as _q

QUARANTINE_BLOCKLIST = _q.HARD_BLOCK_IDS
QUARANTINE_BATCH_IDS = _q.HARD_BLOCK_BATCHES


def _is_blocked(
    chunk_id: str | None,
    record_id: str | None,
    text: str = "",
    batch_id: str | None = None,
    metadata: dict | None = None,
) -> str | None:
    meta = metadata or {}
    return _q.is_blocked((chunk_id, record_id), batch_id=batch_id, batches=_q.find_batches(meta))


# RW-1 hardening knobs (image ENV defaults; not Railway service variables)
DEPLOY_MODE = os.getenv("MEMORY_DEPLOY_MODE", "0") == "1"  # disables DELETE /chunk, /link, /docs
MAX_RECORDS_PER_INGEST = int(os.getenv("MEMORY_MAX_RECORDS", "256"))
_SAFE_PROJECT = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_EXPORT_FORMATS = {"json", "jsonl"}
# Canonical stored fields that caller metadata may NOT overwrite
_RESERVED_META = {"chunk_id", "record_id", "text", "project_id", "highlight_score", "source_type", "redaction_flag"}


router = APIRouter(prefix="/memory", tags=["memory"])


class IngestItem(BaseModel):
    # extra="allow": unknown top-level fields are kept so nested batch refs are still checked + stored
    model_config = ConfigDict(extra="allow")

    id: Optional[str] = None
    text: str
    project_id: str = "highlightai-pending"
    highlight_score: float = 0.5
    source_type: str = "documentation"
    redaction_flag: bool = False
    record_id: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    provenance: Optional[dict[str, Any]] = None
    batch_id: Optional[Any] = None


class IngestBody(BaseModel):
    project_id: str = "highlightai-pending"
    records: list[IngestItem] = Field(default_factory=list)
    # also accept flat single-record fields
    text: Optional[str] = None
    id: Optional[str] = None
    highlight_score: Optional[float] = None
    source_type: Optional[str] = None


class QueryBody(BaseModel):
    query: str
    project_id: str = "highlightai-pending"
    top_k: int = Field(default=8, ge=1, le=50)
    min_highlight_score: Optional[float] = None
    source_type: Optional[str] = None
    expand: bool = True


class LinkBody(BaseModel):
    source_id: str
    target_id: str
    relation: str = "related_to"
    project_id: str = "highlightai-pending"
    properties: dict[str, Any] = Field(default_factory=dict)


@router.post("/ingest")
def ingest(body: IngestBody) -> dict[str, Any]:
    rt = get_runtime()
    items = list(body.records)
    if body.text:
        items.append(
            IngestItem(
                id=body.id,
                text=body.text,
                project_id=body.project_id,
                highlight_score=body.highlight_score if body.highlight_score is not None else 0.5,
                source_type=body.source_type or "documentation",
            )
        )
    if not items:
        raise HTTPException(status_code=400, detail="no_records")
    if len(items) > MAX_RECORDS_PER_INGEST:
        raise HTTPException(status_code=413, detail=f"too_many_records>{MAX_RECORDS_PER_INGEST}")
    if _q.fail_closed():
        rt.audit.log("ingest_refused_fail_closed", errors=_q.load_errors()[:5])
        raise HTTPException(status_code=503, detail="quarantine_config_unparseable_fail_closed")
    accepted: list[str] = []
    blocked_ids: list[str] = []
    pii_blocked: list[dict[str, str]] = []
    for item in items:
        if item.redaction_flag:
            continue
        chunk_id = item.id or f"chk-{uuid4().hex[:16]}"
        record_id = item.record_id or chunk_id
        # B1: whole-record scan (top-level, metadata, metadata.provenance, provenance, extras, any nesting)
        blocked = _q.is_blocked(
            (chunk_id, record_id),
            batches=_q.find_batches(item.model_dump()),
        ) or _q.record_blocked(item.model_dump())
        if blocked:
            blocked_ids.append(blocked)
            rt.audit.log("ingest_blocked_quarantine", chunk_id=chunk_id, record_id=record_id, blocked=blocked)
            continue
        pii = _q.pii_refusal(item.text, item.metadata, item.redaction_flag)
        if pii:
            pii_blocked.append({"chunk_id": chunk_id, "reason": pii})
            rt.audit.log("ingest_blocked_pii", chunk_id=chunk_id, record_id=record_id, reason=pii)
            continue
        vec = rt.embedder.embed_one(item.text)
        user_meta = {k: v for k, v in (item.metadata or {}).items() if k not in _RESERVED_META}
        extras = {k: v for k, v in (item.model_extra or {}).items() if k not in _RESERVED_META}
        meta = {
            **extras,
            **user_meta,
            **({"top_provenance": item.provenance} if item.provenance else {}),
            **({"top_batch_id": item.batch_id} if item.batch_id is not None else {}),
            "chunk_id": chunk_id,
            "record_id": record_id,
            "text": item.text,
            "project_id": item.project_id or body.project_id,
            "highlight_score": float(item.highlight_score),
            "source_type": item.source_type,
            "redaction_flag": bool(item.redaction_flag),
        }
        rt.index.add(chunk_id, vec, meta)
        rt.graph.add_node(record_id, "record", {"project_id": meta["project_id"]}, meta["project_id"])
        rt.graph.add_node(chunk_id, "chunk", {"record_id": record_id}, meta["project_id"])
        rt.graph.add_edge(record_id, chunk_id, "has_chunk", project_id=meta["project_id"])
        accepted.append(chunk_id)
        rt.audit.log("ingest", chunk_id=chunk_id, project_id=meta["project_id"])
    rt.index.save()
    return {
        "accepted": len(accepted),
        "rejected": len(items) - len(accepted),
        "chunk_ids": accepted,
        "blocked_quarantine": blocked_ids,
        "blocked_pii": pii_blocked,
        "job_id": f"job_{uuid4().hex[:8]}",
    }


@router.post("/query")
def query(body: QueryBody) -> dict[str, Any]:
    rt = get_runtime()
    result = rt.retrieval.query(
        body.query,
        project_id=body.project_id,
        top_k=body.top_k,
        min_highlight_score=body.min_highlight_score,
        source_type=body.source_type,
        expand=body.expand,
    )
    hits = result.get("hits") or []
    kept = [
        h for h in hits
        if not _q.meta_blocked({"m": h.get("metadata") or {}, "chunk_id": h.get("chunk_id"), "record_id": h.get("record_id")})
    ]
    if len(kept) != len(hits):
        rt.audit.log("query_filtered_quarantine", removed=len(hits) - len(kept))
    result["hits"] = kept
    result["graph_edges"] = [
        e for e in (result.get("graph_edges") or [])
        if not _q.is_blocked((e.get("source_id"), e.get("target_id")))
    ]
    rt.audit.log("query", project_id=body.project_id, hits=len(result.get("hits") or []))
    return result


@router.post("/link")
def link(body: LinkBody) -> dict[str, Any]:
    if DEPLOY_MODE:
        raise HTTPException(status_code=403, detail="disabled_in_deploy_mode")
    rt = get_runtime()
    rt.graph.add_edge(
        body.source_id,
        body.target_id,
        body.relation,
        properties=body.properties,
        project_id=body.project_id,
    )
    rt.audit.log("link", source_id=body.source_id, target_id=body.target_id, relation=body.relation)
    return {
        "source_id": body.source_id,
        "target_id": body.target_id,
        "relation": body.relation,
        "project_id": body.project_id,
        "status": "ok",
    }


@router.get("/chunk/{chunk_id}")
def get_chunk(chunk_id: str) -> dict[str, Any]:
    rt = get_runtime()
    if _q.is_blocked((chunk_id,)):
        raise HTTPException(status_code=403, detail="quarantined")
    meta = rt.index.get(chunk_id)
    if not meta:
        raise HTTPException(status_code=404, detail="not_found")
    if _q.meta_blocked(meta):
        rt.audit.log("chunk_refused_quarantine", chunk_id=chunk_id)
        raise HTTPException(status_code=403, detail="quarantined")
    return {"chunk_id": chunk_id, **meta}


@router.delete("/chunk/{chunk_id}")
def delete_chunk(chunk_id: str) -> dict[str, Any]:
    if DEPLOY_MODE:
        raise HTTPException(status_code=403, detail="disabled_in_deploy_mode")
    rt = get_runtime()
    ok = rt.index.delete(chunk_id)
    rt.index.save()
    rt.audit.log("delete", chunk_id=chunk_id, removed=ok)
    if not ok:
        raise HTTPException(status_code=404, detail="not_found")
    return {"chunk_id": chunk_id, "removed": True}


@router.get("/export")
def export(
    project_id: str = Query(default="highlightai-pending"),
    format: str = Query(default="jsonl"),
) -> dict[str, Any]:
    if not _SAFE_PROJECT.match(project_id or ""):
        raise HTTPException(status_code=400, detail="invalid_project_id")
    if format not in _EXPORT_FORMATS:
        raise HTTPException(status_code=400, detail="invalid_format")
    rt = get_runtime()
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = config.EXPORT_DIR / f"export-{project_id}-{ts}.{format}"
    config.EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    for i, cid in enumerate(rt.index._ids):
        if rt.index._deleted[i]:
            continue
        meta = rt.index._meta[i]
        if meta.get("project_id") != project_id:
            continue
        if _q.meta_blocked(meta):
            continue
        rows.append(meta)
    if format == "json":
        dest.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    else:
        with dest.open("w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    return {"path": str(dest), "project_id": project_id, "count": len(rows), "format": format}


@router.get("/stats")
def stats(project_id: str | None = None) -> dict[str, Any]:
    rt = get_runtime()
    total = len(rt.index)
    if project_id:
        n = 0
        for i, cid in enumerate(rt.index._ids):
            if rt.index._deleted[i]:
                continue
            if rt.index._meta[i].get("project_id") == project_id:
                n += 1
        total = n
    g = rt.graph.count()
    return {
        "chunk_count": total,
        "index_len": len(rt.index),
        "deleted_ratio": rt.index.deleted_ratio,
        "graph": g,
        "embedding_dim": rt.embedder.dim,
        "embedder_backend": rt.embedder.backend,
        "production_ready": rt.production_ready,
        "project_id": project_id or config.PROJECT_ID,
    }


@router.get("/health")
def health() -> JSONResponse:
    rt = get_runtime()
    ready = (
        bool(rt.production_ready)
        and rt.embedder.backend == "sentence-transformers"
        and not _q.fail_closed()
    )
    body = {
        "status": "ok" if ready else "degraded",
        "mode": "numpy+sqlite",
        "project_id": config.PROJECT_ID,
        "production_ready": ready,
        "stores_configured": True,
        "embedding_model": rt.embedder.model_name,
        "model": rt.embedder.model_name,
        "embedding_dim": rt.embedder.dim or DIM,
        "embedder_backend": rt.embedder.backend,
        "backend": rt.embedder.backend,
        "index_size": len(rt.index),
        "graph": rt.graph.count(),
        "port": config.MEMORY_PORT,
        "detail": "WAVE2-2.0 MiniLM embeddings + VectorIndex+GraphStore",
        "quarantine": {
            "dir": str(_q.quarantine_dir()),
            "hard_block_ids": sorted(_q.HARD_BLOCK_IDS),
            "hard_block_batches": sorted(_q.HARD_BLOCK_BATCHES),
            "effective_ids": len(_q.blocked_ids()),
            "pii_confidence_threshold": _q.PII_CONFIDENCE_THRESHOLD,
            "fail_closed": _q.fail_closed(),
            "load_errors": _q.load_errors()[:10],
        },
        "deploy_mode": DEPLOY_MODE,
    }
    # RW-1: non-200 when degraded (hash fallback / fail-closed) so Railway never marks it healthy
    return JSONResponse(body, status_code=200 if ready else 503)


# WAVE2-2.0: /v1/* aliases required by Manager acceptance
v1_router = APIRouter(prefix="/v1", tags=["v1"])


@v1_router.get("/health")
def v1_health() -> JSONResponse:
    return health()
