"""HighlightAI Memory — WAVE1-1.2 numpy+sqlite FastAPI on :8092."""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from app import __version__, config
from app.audit import AuditLogger
from app.embedder import Embedder
from app.graph_store import GraphStore
from app.retrieval import RetrievalEngine
from app.routes import router, v1_router
from app.state import MemoryRuntime, set_runtime
from app.vector_index import VectorIndex

# WAVE1 contract default port
config.MEMORY_PORT = int(os.getenv("MEMORY_PORT", "8092"))
config.MEMORY_MODE = "numpy+sqlite"


def _data_dirs() -> dict[str, Path]:
    base = config.MEMORY_ARTIFACTS_DIR
    index_dir = base / "index" / "_wave1"
    graph_path = base / "graph" / "wave1_graph.sqlite"
    audit_path = base / "audit" / "wave1.jsonl"
    # RW-1: MEMORY_MODEL_CACHE lets the image bake MiniLM in (/opt/models) so boot needs no network
    models = Path(os.getenv("MEMORY_MODEL_CACHE") or (base / "models"))
    for p in (index_dir, graph_path.parent, audit_path.parent, models, config.EXPORT_DIR, base / "store"):
        p.mkdir(parents=True, exist_ok=True)
    return {
        "index_dir": index_dir,
        "graph_path": graph_path,
        "audit_path": audit_path,
        "models": models,
        "base": base,
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    dirs = _data_dirs()
    force_hash = os.getenv("FORCE_HASH_EMBED", "0") == "1"
    # WAVE2-2.0: never silently stay on hash for serve
    from app.embedder import EmbedderLoadError

    try:
        embedder = Embedder(
            cache_folder=str(dirs["models"]),
            force_hash=force_hash,
            allow_hash_fallback=False,
        )
    except EmbedderLoadError:
        # Last-resort: allow start on hash but mark not production_ready + audit blocker
        embedder = Embedder(
            cache_folder=str(dirs["models"]),
            force_hash=False,
            allow_hash_fallback=True,
        )
    from app import quarantine

    quarantine.seed_manifest()
    qstats = quarantine.load_quarantine_dir()
    index = VectorIndex(dirs["index_dir"], dim=embedder.dim)
    graph = GraphStore(dirs["graph_path"])
    retrieval = RetrievalEngine(embedder, index, graph, min_highlight_score=0.25)
    audit = AuditLogger(dirs["audit_path"])
    prod = embedder.backend == "sentence-transformers"
    if not prod:
        audit.log(
            "embedder_blocker",
            backend=embedder.backend,
            error=getattr(embedder, "load_error", None),
        )
    rt = MemoryRuntime(
        embedder=embedder,
        index=index,
        graph=graph,
        retrieval=retrieval,
        audit=audit,
        data_dir=dirs["base"],
        production_ready=prod,
    )
    set_runtime(rt)
    audit.log(
        "startup",
        backend=embedder.backend,
        dim=embedder.dim,
        port=config.MEMORY_PORT,
        quarantine_dir=str(quarantine.quarantine_dir()),
        hard_block_ids=len(quarantine.HARD_BLOCK_IDS),
        hard_block_batches=sorted(quarantine.HARD_BLOCK_BATCHES),
        **qstats,
    )
    try:
        yield
    finally:
        try:
            index.save()
        except Exception:
            pass
        try:
            graph.close()
        except Exception:
            pass
        audit.log("shutdown")
        set_runtime(None)


_DEPLOY_MODE = os.getenv("MEMORY_DEPLOY_MODE", "0") == "1"
_MAX_BODY = int(os.getenv("MEMORY_MAX_BODY_BYTES", str(2 * 1024 * 1024)))

app = FastAPI(
    # RW-1: no /docs, /redoc, /openapi.json in deploy mode
    docs_url=None if _DEPLOY_MODE else "/docs",
    redoc_url=None if _DEPLOY_MODE else "/redoc",
    openapi_url=None if _DEPLOY_MODE else "/openapi.json",
    title="HighlightAI Memory",
    version=__version__,
    description="WAVE1-1.2 local numpy memmap + SQLite graph memory service",
    lifespan=lifespan,
)


@app.middleware("http")
async def _limit_body(request, call_next):
    """RW-1: cap request bodies (Content-Length and streamed)."""
    from fastapi.responses import JSONResponse

    cl = request.headers.get("content-length")
    if cl is not None:
        try:
            if int(cl) > _MAX_BODY:
                return JSONResponse({"detail": "body_too_large"}, status_code=413)
        except ValueError:
            return JSONResponse({"detail": "bad_content_length"}, status_code=400)
    elif request.method in ("POST", "PUT", "PATCH"):
        body = await request.body()
        if len(body) > _MAX_BODY:
            return JSONResponse({"detail": "body_too_large"}, status_code=413)
    return await call_next(request)


app.include_router(router)
app.include_router(v1_router)


@app.get("/")
def root() -> dict:
    return {
        "service": "highlightai-memory",
        "version": __version__,
        "mode": "numpy+sqlite",
        "project_id": config.PROJECT_ID,
        "docs": None if _DEPLOY_MODE else "/docs",
        "health": "/memory/health",
        "port": config.MEMORY_PORT,
    }


def run() -> None:
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=config.MEMORY_HOST,
        port=config.MEMORY_PORT,
        log_level="info",
    )


if __name__ == "__main__":
    run()
