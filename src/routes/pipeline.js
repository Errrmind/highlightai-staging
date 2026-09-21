const express = require('express');
const { evaluatePipelineHealth } = require('../lib/bottleneck');
const { logSkill } = require('../lib/audit');

const router = express.Router();

router.get('/pipeline/health', (_req, res) => {
  const health = evaluatePipelineHealth();
  logSkill('agent.orchestrator', 'pipeline.health', { proposal_id: health.proposal_id, bottleneck: health.bottleneck, p99_gap: health.p99_gap });
  res.json(health);
});

module.exports = router;
