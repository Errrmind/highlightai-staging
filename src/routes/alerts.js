const express = require('express');
const { getRecent, getSince } = require('../lib/alertsProxy');
const { logSkill } = require('../lib/audit');

const router = express.Router();

router.get('/api/alerts/recent', async (req, res) => {
  try {
    const limit = Number(req.query.limit || 20);
    const data = await getRecent(limit);
    logSkill('agent.orchestrator', 'alerts.recent', { backend: data.backend, count: data.count || (data.alerts && data.alerts.length) });
    res.json(data);
  } catch (e) {
    res.status(500).json({ error: String(e.message || e) });
  }
});

router.get('/api/alerts', async (req, res) => {
  try {
    const data = await getSince(req.query.since, Number(req.query.limit || 50));
    logSkill('agent.orchestrator', 'alerts.list', { backend: data.backend, since: req.query.since || null });
    res.json(data);
  } catch (e) {
    res.status(500).json({ error: String(e.message || e) });
  }
});

module.exports = router;
