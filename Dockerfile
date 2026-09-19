FROM node:20-alpine AS runner
WORKDIR /app
COPY package.json package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci --omit=dev; else npm install --omit=dev; fi && npm cache clean --force
COPY src ./src
COPY public ./public
COPY scripts ./scripts
ENV NODE_ENV=production
ENV HOST=0.0.0.0
ENV PORT=4310
ENV HA_ROOT=/data/highlightai
RUN mkdir -p /data/highlightai/audit /data/highlightai/artifacts/orchestrator /data/highlightai/artifacts/memory
EXPOSE 4310
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD node scripts/health-check.js || exit 1
CMD ["npm", "start"]
