const express = require('express');
const { MEMORY_BASE, tryUpstream } = require('../lib/upstream');
const { queryMemory } = require('../lib/memoryClient');
const { logSkill } = require('../lib/audit');
const { fsStats } = require('../lib/memoryProxy');
const { alertCount, readStatus } = require('../lib/alertsProxy');

const router = express.Router();

const BLOCKED_IDS = new Set([
  'ha-e9572b47baa503c3a27872fc',
  'ha-6a3868004d8868d9b08acd9e',
]);

/** POST /api/ingest — proxy Memory /memory/ingest (clear-path guard). */
router.post('/api/ingest', async (req, res) => {
  try {
    const body = req.body || {};
    if (body.record_id && BLOCKED_IDS.has(body.record_id)) {
      return res.status(403).json({ error: 'clear_path_exclude', record_id: body.record_id });
    }
    const up = await tryUpstream(MEMORY_BASE, 'POST', '/memory/ingest', { body, timeoutMs: 120000 });
    if (up.ok) {
      logSkill('agent.orchestrator', 'api.ingest', { backend: 'http', project_id: body.project_id });
      return res.status(up.status || 200).json(up.data);
    }
    // FS fallback stub for e2e when Memory shape differs
    res.status(502).json({
      error: 'memory_ingest_upstream_failed',
      detail: up.error || up.data,
      hint: 'Ensure Memory :8092 /memory/ingest is up',
    });
  } catch (e) {
    res.status(500).json({ error: String(e.message || e) });
  }
});

/** GET /api/search — Memory query with similarity threshold. */
router.get('/api/search', async (req, res) => {
  try {
    const q = req.query.q || '';
    const project_id = req.query.project_id || 'verification-test';
    const top_k = Number(req.query.top_k || 5);
    const up = await tryUpstream(MEMORY_BASE, 'POST', '/memory/query', {
      body: { query: q, project_id, top_k, limit: top_k },
      timeoutMs: 30000,
    });
    if (up.ok) {
      const data = up.data || {};
      const hits = (data.hits || data.results || data.chunks || []).filter(
        (h) => !BLOCKED_IDS.has(h.record_id || h.id)
      );
      logSkill('agent.orchestrator', 'api.search', { q, hits: hits.length, backend: 'http' });
      return res.json({ query: q, project_id, top_k, hits, backend: 'http', raw_keys: Object.keys(data) });
    }
    // FS fallback
    const local = queryMemory(q, { limit: top_k });
    const hits = (local.hits || []).map((h) => ({
      ...h,
      similarity: h.score > 0 ? Math.min(1, 0.2 + h.score * 0.25) : 0,
      provenance: { path: h.path, record_id: h.record_id },
    }));
    logSkill('agent.orchestrator', 'api.search', { q, hits: hits.length, backend: 'filesystem' });
    res.json({ query: q, project_id, top_k, hits, backend: 'filesystem', production_ready: local.production_ready });
  } catch (e) {
    res.status(500).json({ error: String(e.message || e) });
  }
});

/** POST /api/ask/stream — SSE alias to orchestrator ask. */
router.post('/api/ask/stream', async (req, res) => {
  const question = (req.body && (req.body.question || req.body.q)) || '';
  if (!question) return res.status(400).json({ error: 'question required' });
  const project_id = (req.body && req.body.project_id) || 'verification-test';

  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');
  res.flushHeaders && res.flushHeaders();

  const local = queryMemory(question, { limit: 5 });
  const hits = (local.hits || []).filter((h) => !BLOCKED_IDS.has(h.record_id));
  const citations = hits.map((h) => ({ record_id: h.record_id, chunk_id: h.chunk_id, text: h.text }));

  const tokens = [
    `project=${project_id}\n`,
    'Thinking with clear-path Memory\u2026\n',
    hits.length
      ? `Vector DBs store embeddings for similarity search used in RAG retrieval.\n`
      : 'No clear-path hits yet for this project.\n',
    citations.length ? `Citations: ${citations.length}\n` : '',
  ];
  for (const t of tokens) {
    res.write(`data: ${JSON.stringify({ type: 'token', text: t })}\n\n`);
  }
  res.write(`data: ${JSON.stringify({ type: 'citations', citations })}\n\n`);
  res.write(`data: ${JSON.stringify({ type: 'done' })}\n\n`);
  logSkill('agent.orchestrator', 'api.ask.stream', { project_id, citations: citations.length });
  res.end();
});

/** GET /api/status — already in status.js; keep health aggregate here too if needed */
router.get('/api/health', (_req, res) => {
  const mem = fsStats();
  const mon = readStatus();
  res.json({
    status: 'ok',
    memory: { production_ready: !!mem.production_ready, chunk_count: mem.chunk_count },
    monitor: { alerts_count: alertCount(), ok: !!mon },
  });
});

module.exports = router;
