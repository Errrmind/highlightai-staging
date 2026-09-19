#!/bin/sh
set -e
export HOST="${HOST:-0.0.0.0}"
export PORT="${PORT:-4310}"
export HA_ROOT="${HA_ROOT:-$(cd "$(dirname "$0")/.." && pwd)/data}"
mkdir -p "$HA_ROOT/audit" "$HA_ROOT/artifacts/orchestrator" "$HA_ROOT/artifacts/memory"
exec node src/index.js
