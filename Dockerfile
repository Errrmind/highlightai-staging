# HighlightAI Orchestrator — Railway / container deploy (clear-path)
FROM node:20-alpine AS runner
WORKDIR /app

COPY package.json package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci --omit=dev; else npm install --omit=dev; fi && npm cache clean --force

COPY src ./src
COPY public ./public
COPY scripts ./scripts
COPY spa/dist ./spa/dist
COPY data/humangate-seed ./data/humangate-seed

ENV NODE_ENV=production
ENV HOST=0.0.0.0
ENV PORT=4310
ENV HA_ROOT=/data/highlightai
ENV HUMANGATE_STATE_ROOT=/data/highlightai/services/humangate/state
ENV HUMANGATE_AUDIT=/data/highlightai/audit/gates.jsonl
ENV HUMANGATE_SEED_ROOT=/app/data/humangate-seed

RUN mkdir -p /data/highlightai/audit /data/highlightai/artifacts/orchestrator /data/highlightai/artifacts/memory \
  /data/highlightai/services/humangate/state/pending \
  /data/highlightai/services/humangate/state/approved \
  /data/highlightai/services/humangate/state/rejected \
  /data/highlightai/services/humangate/state/escalated

EXPOSE 4310
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD node scripts/health-check.js || exit 1

CMD ["npm", "start"]
