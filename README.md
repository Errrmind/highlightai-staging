# HA Orchestrator (CORE-BUILD-V1)

Local-only Node/Express service for HighlightAI Omni-Orchestrator.

```bash
cd /workspace/highlightai/services/orchestrator
npm install
npm start   # http://127.0.0.1:4310
```

Key routes: `/orchestrator/health`, `/metrics`, `/orchestrator/ask/stream`, `/orchestrator/auth/session`, task CRUD under `/orchestrator/tasks`.
