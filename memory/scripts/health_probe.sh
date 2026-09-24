#!/usr/bin/env bash
# Operator-run ONLY when Manager publishes the memory cluster base URL.
# Do NOT run from agent/scaffold sessions. Do NOT probe localhost by default.
#
# Usage:
#   MEMORY_BASE_URL=https://memory.example.cluster ./scripts/health_probe.sh
set -euo pipefail

BASE_URL="${MEMORY_BASE_URL:-}"
if [[ -z "${BASE_URL}" ]]; then
  echo "health_probe: MEMORY_BASE_URL unset — refusing to probe localhost." >&2
  echo "Set MEMORY_BASE_URL to the cluster service URL from Manager, then retry." >&2
  exit 2
fi

# Guard against accidental localhost probes during scaffold.
case "${BASE_URL}" in
  http://127.*|http://localhost*|https://127.*|https://localhost*)
    if [[ "${ALLOW_LOCALHOST_PROBE:-}" != "1" ]]; then
      echo "health_probe: refusing localhost probe (set ALLOW_LOCALHOST_PROBE=1 to override)." >&2
      exit 2
    fi
    ;;
esac

URL="${BASE_URL%/}/memory/health"
echo "Probing ${URL}"
curl -fsS --max-time 10 "${URL}" | tee /tmp/ha-memory-health.json
echo
