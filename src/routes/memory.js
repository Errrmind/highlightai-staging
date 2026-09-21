const express = require('express');
const { getStats, getChunk, exportChunks } = require('../lib/memoryProxy');
const { logSkill } = require('../lib/audit');

const router = express.Router();

router.get('/api/memory/stats', async (_req, res) => {
  try {
    const stats = await getStats();
    logSkill('agent.orchestrator', 'memory.stats', { backend: stats.backend, production_ready: stats.production_ready });
    res.json(stats);
  } catch (e) {
    res.status(500).json({ error: String(e.message || e) });
  }
});

router.get('/api/memory/chunk/:id', async (req, res) => {
  try {
    const hit = await getChunk(req.params.id);
    if (!hit) return res.status(404).json({ error: 'chunk not found', id: req.params.id });
    logSkill('agent.orchestrator', 'memory.chunk', { id: req.params.id, backend: hit.backend });
    res.json(hit);
  } catch (e) {
    res.status(500).json({ error: String(e.message || e) });
  }
});

async function handleExport(req, res) {
  try {
    const limit = Number((req.query && req.query.limit) || (req.body && req.body.limit) || 100);
    const data = await exportChunks({ limit });
    logSkill('agent.orchestrator', 'memory.export', { backend: data.backend, count: data.count || (data.chunks && data.chunks.length) });
    res.json(data);
  } catch (e) {
    res.status(500).json({ error: String(e.message || e) });
  }
}

router.get('/api/memory/export', handleExport);
router.post('/api/memory/export', handleExport);

module.exports = router;
