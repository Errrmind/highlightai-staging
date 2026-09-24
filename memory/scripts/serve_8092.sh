#!/usr/bin/env bash
# WAVE2-2.0 serve — real MiniLM (never force hash)
set -euo pipefail
cd "$(dirname "$0")/.."
export MEMORY_PORT="${MEMORY_PORT:-8092}"
export MEMORY_HOST="${MEMORY_HOST:-127.0.0.1}"
unset FORCE_HASH_EMBED || true
export FORCE_HASH_EMBED=0
exec .venv/bin/uvicorn app.main:app --host "$MEMORY_HOST" --port "$MEMORY_PORT"
