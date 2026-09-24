"""Memory service config — CORE-BUILD-V1 local-only mode."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(os.getenv("HIGHLIGHTAI_ROOT", "/workspace/highlightai")).resolve()

PROJECT_ID = os.getenv("PROJECT_ID", "highlightai-pending")
MEMORY_MODE = os.getenv("MEMORY_MODE", "filesystem")  # filesystem | cluster

CLEANER_OUT_DIR = ROOT / os.getenv("CLEANER_OUT_DIR", "artifacts/cleaner/out")
CLEANER_QUARANTINE_DIR = ROOT / os.getenv(
    "CLEANER_QUARANTINE_DIR", "artifacts/cleaner/quarantine"
)
SECURITY_DIR = ROOT / os.getenv("SECURITY_DIR", "artifacts/security")
MEMORY_ARTIFACTS_DIR = ROOT / os.getenv("MEMORY_ARTIFACTS_DIR", "artifacts/memory")
SCHEMA_PATH = ROOT / "schemas" / "canonical-v2.1.json"
AUDIT_PATH = ROOT / "audit" / "memory.jsonl"

# CORE-BUILD-V1: local embeddings only (no OpenAI)
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
EMBEDDING_DIMENSIONS = int(os.getenv("EMBEDDING_DIMENSIONS", "384"))
EMBED_BATCH_SIZE = int(os.getenv("EMBED_BATCH_SIZE", "64"))
MODEL_CACHE_DIR = MEMORY_ARTIFACTS_DIR / "models"
FORCE_HASH_EMBED = os.getenv("FORCE_HASH_EMBED", "0") == "1"

CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "512"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "64"))
RETENTION_DAYS = int(os.getenv("RETENTION_DAYS", "90"))

MEMORY_HOST = os.getenv("MEMORY_HOST", "0.0.0.0")
MEMORY_PORT = int(os.getenv("MEMORY_PORT", os.getenv("PORT", "8092")))

STATUS_MD = MEMORY_ARTIFACTS_DIR / "STATUS.md"
HEALTH_JSON = MEMORY_ARTIFACTS_DIR / "health.json"
EXPORT_DIR = MEMORY_ARTIFACTS_DIR / "exports"
STORE_DIR = MEMORY_ARTIFACTS_DIR / "store"
INDEX_DIR = MEMORY_ARTIFACTS_DIR / "index"
GRAPH_DIR = MEMORY_ARTIFACTS_DIR / "graph"

# Deprecated cluster knobs kept for compatibility; unused in local_only
QDRANT_URL = None
NEO4J_URI = None
OPENAI_API_KEY = None


def stores_configured() -> bool:
    return True  # local npy + sqlite always available


def cluster_ready() -> bool:
    return False
