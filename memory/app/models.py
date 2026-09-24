"""Pydantic models aligned to schemas/canonical-v2.1.json."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, HttpUrl


class Entity(BaseModel):
    type: str
    value: str
    confidence: Optional[float] = Field(default=None, ge=0, le=1)


class Provenance(BaseModel):
    source_url: str
    crawl_timestamp: datetime
    license_header: Optional[str] = None
    batch_id: Optional[str] = None


class Metadata(BaseModel):
    project_id: str = "highlightai-pending"
    chat_id: Optional[str] = None
    pii_flag: bool = False
    pii_confidence: Optional[float] = Field(default=None, ge=0, le=1)
    redaction_flag: bool = False
    quarantined: bool = False


class CanonicalRecord(BaseModel):
    """Canonical v2.1 record — ingest input unit."""

    id: str = Field(..., min_length=1)
    text: str
    language: Optional[str] = None
    content_type: Optional[str] = None
    entities: list[Entity] = Field(default_factory=list)
    provenance: Provenance
    metadata: Metadata


class Chunk(BaseModel):
    chunk_id: str
    record_id: str
    text: str
    index: int
    start: int
    end: int
    project_id: str
    created_at: datetime
    expires_at: datetime
    pii_flag: bool = False
    embedding: Optional[list[float]] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class IngestRequest(BaseModel):
    """Trigger ingest from cleaner out/ after security gate."""

    project_id: str = "highlightai-pending"
    dry_run: bool = False
    fixture_mode: bool = False  # bypass cleaner/security gates for eval/tests
    records: list[CanonicalRecord] = Field(default_factory=list)
    source_jsonl: Optional[str] = None


class IngestResult(BaseModel):
    accepted: bool
    reason: str
    records_seen: int = 0
    chunks_created: int = 0
    skipped_quarantined: int = 0
    skipped_pii: int = 0
    blocked_by: list[str] = Field(default_factory=list)


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1)
    project_id: str = "highlightai-pending"
    top_k: int = Field(default=8, ge=1, le=50)
    include_graph: bool = True


class QueryHit(BaseModel):
    chunk_id: str
    record_id: str
    text: str
    score: float
    step: Literal["vector", "graph", "rerank", "assemble", "embed", "filter_metadata", "graph_expand"]
    metadata: dict[str, Any] = Field(default_factory=dict)


class QueryResponse(BaseModel):
    query: str
    project_id: str
    hits: list[QueryHit]
    steps: list[str]
    mode: str
    step4_handoff: dict[str, Any] = Field(default_factory=dict)


class GetByIdRequest(BaseModel):
    id: str
    project_id: str = "highlightai-pending"


class LinkRequest(BaseModel):
    source_id: str
    target_id: str
    relation: str = "related_to"
    project_id: str = "highlightai-pending"
    properties: dict[str, Any] = Field(default_factory=dict)


class DeleteRequest(BaseModel):
    id: str
    project_id: str = "highlightai-pending"
    hard: bool = False


class ExportRequest(BaseModel):
    project_id: str = "highlightai-pending"
    format: Literal["jsonl", "json"] = "jsonl"


class HealthResponse(BaseModel):
    status: str
    mode: str
    project_id: str
    stores_configured: bool
    ingest_gates: dict[str, bool]
    embedding_model: str
    chunk_size: int
    chunk_overlap: int
    retention_days: int
    detail: str
