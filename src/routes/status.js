const express = require('express');
const { fsStats } = require('../lib/memoryProxy');
const { alertCount, readStatus } = require('../lib/alertsProxy');
const { evaluatePipelineHealth } = require('../lib/bottleneck');
const { logSkill } = require('../lib/audit');

const router = express.Router();

router.get('/api/status', (_req, res) => {
  const mem = fsStats();
  const mon = readStatus();
  const alerts = alertCount();
  const pipeline = evaluatePipelineHealth();
  const body = {
    status: 'ok',
    bot: 'agent.orchestrator',
    task: 'CORE-BUILD-V1',
    project_id: 'highlightai-pending',
    wave: 'WAVE1-1.5',
    memory: {
      production_ready: !!mem.production_ready,
      mode: mem.mode,
      chunk_count: mem.chunk_count,
      backend: mem.backend,
    },
    monitor: {
      alerts_count: alerts,
      alerts_dispatched: mon ? Number(mon.alerts_dispatched || alerts) : alerts,
      anomaly_count: mon ? Number(mon.anomaly_count || 0) : null,
      p99_detect_sec: mon ? mon.p99_detect_sec : null,
    },
    pipeline_health: {
      bottleneck: pipeline.bottleneck,
      p99_gap: pipeline.p99_gap,
      enabled: pipeline.enabled,
    },
    railway_soft_refresh: false,
  };
  logSkill('agent.orchestrator', 'api.status', { memory_production_ready: body.memory.production_ready, alerts_count: alerts });
  res.json(body);
});

module.exports = router;
