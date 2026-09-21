const fs = require('fs');
const path = require('path');

const CONFIG_PATH =
  process.env.HA_BOTTLENECK_CONFIG ||
  path.join(process.env.HA_ROOT || '/workspace/highlightai', 'config/pipeline-bottleneck.v1.json');

function loadConfig() {
  try {
    return JSON.parse(fs.readFileSync(CONFIG_PATH, 'utf8'));
  } catch {
    return { enabled: false };
  }
}

function readMonitorStatus(cfg) {
  const candidates = [cfg.monitor_status_path, cfg.monitor_status_fallback].filter(Boolean);
  for (const p of candidates) {
    try {
      if (fs.existsSync(p)) return { path: p, data: JSON.parse(fs.readFileSync(p, 'utf8')) };
    } catch (_) {}
  }
  return { path: null, data: null };
}

/** Soft bottleneck + P99 gap snapshot for queue ranking / hand-off gates. */
function evaluatePipelineHealth() {
  const cfg = loadConfig();
  if (!cfg.enabled) {
    return { enabled: false, bottleneck: false, p99_gap: false, ranking_adjust: 0, warnings: [] };
  }
  const { data, path: statusPath } = readMonitorStatus(cfg);
  const warnings = [];
  let bottleneck = false;
  let p99_gap = false;
  let ranking_adjust = 0;

  if (!data) {
    warnings.push('monitor_status_unavailable');
    return { enabled: true, bottleneck: false, p99_gap: false, ranking_adjust: 0, warnings, statusPath, config: CONFIG_PATH };
  }

  const alerts = Number(data.alerts_dispatched || data.anomaly_count || 0);
  const anomalies = Number(data.anomaly_count || 0);
  const minAlerts = (cfg.soft_bottleneck && cfg.soft_bottleneck.min_repeated_alerts) || 3;
  const anomWarn = (cfg.soft_bottleneck && cfg.soft_bottleneck.anomaly_count_warn) || 10;

  if (alerts >= minAlerts || anomalies >= anomWarn) {
    bottleneck = true;
    warnings.push(`soft_bottleneck:alerts=${alerts},anomalies=${anomalies}`);
    ranking_adjust -= (cfg.queue_ranking && cfg.queue_ranking.penalize_if_bottleneck) || 25;
  }

  const p99 = Number(data.p99_detect_sec != null ? data.p99_detect_sec : (data.p99_detect_ms || 0) / 1000);
  const budget = (cfg.p99_detect && cfg.p99_detect.budget_sec) || 5;
  if (cfg.p99_detect && cfg.p99_detect.surface_into_queue_ranking && p99 > budget) {
    p99_gap = true;
    const gap = p99 - budget;
    warnings.push(`p99_detect_gap_sec=${gap.toFixed(3)} (p99=${p99}, budget=${budget})`);
    ranking_adjust += (cfg.queue_ranking && cfg.queue_ranking.boost_if_p99_gap) || 15;
    // weight gap magnitude lightly
    ranking_adjust += Math.min(50, gap * ((cfg.p99_detect && cfg.p99_detect.gap_ranking_weight) || 10));
  }

  return {
    enabled: true,
    bottleneck,
    p99_gap,
    p99_detect_sec: p99,
    p99_budget_sec: budget,
    alerts_dispatched: alerts,
    anomaly_count: anomalies,
    ranking_adjust,
    warn_only: !!(cfg.soft_bottleneck && cfg.soft_bottleneck.warn_only),
    block_hand_off: !!(cfg.soft_bottleneck && cfg.soft_bottleneck.block_hand_off && bottleneck),
    stages_before_hand_off: cfg.stages_before_hand_off || ['formatter', 'executor'],
    warnings,
    statusPath,
    proposal_id: cfg.proposal_id,
    config: CONFIG_PATH,
  };
}

function rankTask(task, health) {
  const cfg = loadConfig();
  const baseMap = (cfg.queue_ranking && cfg.queue_ranking.base_priority) || {
    critical: 100,
    high: 50,
    normal: 10,
    low: 1,
  };
  const pri = (task && task.priority) || 'normal';
  let score = baseMap[pri] != null ? baseMap[pri] : baseMap.normal;
  if (health && health.enabled) score += health.ranking_adjust || 0;
  // demote formatter/executor hand-off candidates when soft bottleneck
  const tags = (task && task.capability_tags) || [];
  const stages = (health && health.stages_before_hand_off) || [];
  if (health && health.bottleneck && tags.some((t) => stages.includes(t))) {
    score -= 20;
  }
  return score;
}

function softCheckHandOff(stage, health) {
  const h = health || evaluatePipelineHealth();
  const stages = h.stages_before_hand_off || ['formatter', 'executor'];
  if (!stages.includes(stage)) return { ok: true, health: h };
  if (h.block_hand_off) return { ok: false, reason: 'soft_bottleneck_block', health: h };
  return { ok: true, soft_warn: h.bottleneck || h.p99_gap, health: h };
}

module.exports = { loadConfig, evaluatePipelineHealth, rankTask, softCheckHandOff, CONFIG_PATH };
