# HA Orchestrator (CORE-BUILD-V1)

Local-only Node/Express service for HighlightAI Omni-Orchestrator.

```bash
cd /workspace/highlightai/services/orchestrator
npm install
npm start   # http://127.0.0.1:4310
```

Key routes: `/orchestrator/health`, `/metrics`, `/orchestrator/ask/stream`, `/orchestrator/auth/session`, task CRUD under `/orchestrator/tasks`.

## Railway deploy (clear-path staging)

Root Directory: `services/orchestrator`

- **Dockerfile** (default via `railway.toml`) — binds `HOST=0.0.0.0`, honors Railway `PORT`
- **Nixpacks fallback**: `nixpacks.toml` + `Procfile`
- Health: `GET /health` (also `/orchestrator/health`, `/metrics`)
- Env: `PORT` (Railway), `HOST=0.0.0.0`, `HA_ROOT=/data/highlightai` (or `/app/data` on Nixpacks), `ORCH_JWT_SECRET`

```bash
# local docker smoke
docker build -t ha-orchestrator .
docker run --rm -p 4310:4310 -e PORT=4310 ha-orchestrator
curl -s localhost:4310/health
```

Do not enable PII-gated chains (ha-e9572b47 / batch-002/003) on this service.
