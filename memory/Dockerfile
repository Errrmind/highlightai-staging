# HighlightAI Memory — Railway image (RW-1)
# Based on HA-Memory's services/memory/Dockerfile (python:3.12-slim + requirements-deploy.txt).
# RW-1 changes: torch installed from the CPU-only index explicitly, MiniLM baked into the
# image (/opt/models) so first boot needs no Hugging Face network; data stays on /data.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements-deploy.txt .
RUN pip install --index-url https://download.pytorch.org/whl/cpu "torch>=2.2.0" \
 && pip install -r requirements-deploy.txt

# Pre-download all-MiniLM-L6-v2 into the image (no runtime network needed)
ENV MEMORY_MODEL_CACHE=/opt/models \
    HF_HOME=/opt/hf \
    SENTENCE_TRANSFORMERS_HOME=/opt/models
RUN python -c "from sentence_transformers import SentenceTransformer as S; m=S('sentence-transformers/all-MiniLM-L6-v2', cache_folder='/opt/models'); print('dim', m.get_sentence_embedding_dimension())" \
 && rm -rf /root/.cache

COPY app ./app
COPY scripts ./scripts
COPY seed ./seed

# Runtime defaults (all overridable by Railway service variables)
ENV FORCE_HASH_EMBED=0 \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    MEMORY_HOST=0.0.0.0 \
    MEMORY_PORT=8092 \
    HIGHLIGHTAI_ROOT=/data \
    MEMORY_ARTIFACTS_DIR=memory \
    CLEANER_OUT_DIR=cleaner/out \
    CLEANER_QUARANTINE_DIR=cleaner/quarantine \
    SECURITY_DIR=security

EXPOSE 8092
# HA-Memory launcher: single dual-stack socket [::]:$PORT (IPv4 + IPv6, IPV6_V6ONLY=0).
# Railway private networking (*.railway.internal) needs IPv6; uvicorn --host 0.0.0.0 would be IPv4-only.
CMD ["python", "scripts/serve.py"]
