# HighlightAI Memory — Railway service `ha-memory` (RW-1)

FastAPI app `app.main:app` (numpy VectorIndex + SQLite GraphStore, local
`sentence-transformers/all-MiniLM-L6-v2`, 384-d). No external embedding API; OPENAI_API_KEY is not used.

## Build / run
- `Dockerfile`: python:3.12-slim, CPU-only torch (download.pytorch.org/whl/cpu), `requirements-deploy.txt`,
  MiniLM baked into the image at `/opt/models` (`MEMORY_MODEL_CACHE`, `HF_HUB_OFFLINE=1`) so boot needs no network.
- Start: `python scripts/serve.py`, a dual-stack socket on `[::]:$PORT` (IPv4+IPv6; Railway private networking needs IPv6).
- Health: `GET /v1/health` (alias `/memory/health`), expect `embedder_backend=sentence-transformers`, `production_ready=true`.
- Data: Railway volume at `/data` → `/data/memory/{index,graph,audit,exports}`; quarantine dir `/data/cleaner/quarantine`.
- Railway config-as-code: `railway.toml` (set the config path to `/memory/railway.toml`).

## Service variables (8, no secrets)
PORT, MEMORY_PORT, FORCE_HASH_EMBED, HIGHLIGHTAI_ROOT, MEMORY_ARTIFACTS_DIR, HF_HOME,
SENTENCE_TRANSFORMERS_HOME, PYTHONUNBUFFERED.

## PII / quarantine enforcement (`app/quarantine.py`)
- Permanent excludes (image constants): `ha-e9572b47baa503c3a27872fc`, `ha-e9572b47`,
  `ha-6a3868004d8868d9b08acd9e`, `ha-6a3868004d8868d9b08acd9e-c0`, batch `batch-002`.
  Refused on ingest (`blocked_quarantine`), filtered from query hits and graph edges, 403 on `/memory/chunk/{id}`, skipped by export.
- On boot, `hard-blocks.json` (ids only) is seeded into `CLEANER_QUARANTINE_DIR` and any ids/batches found in `*.json`/`*.jsonl`
  in that directory are also blocked.
- PII gate on ingest: `metadata.quarantined` → refused; `pii_flag` and unredacted and `pii_confidence >= 0.80` → refused;
  unredacted email, phone or SSN pattern → refused (`blocked_pii`).

## Seed (once after the first healthy deploy)
`python scripts/seed_approved.py --base http://localhost:${PORT}` loads 4 approved chunks
(batch-003 plus verification-test fixtures). The script also refuses the permanent excludes on the client side.
