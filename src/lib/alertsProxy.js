const fs = require('fs');
const path = require('path');
const { ROOT } = require('./paths');
const { MONITOR_BASE, tryUpstream } = require('./upstream');

const ALERTS_DIR = path.join(ROOT, 'artifacts/monitor/alerts');
const STATUS_PATHS = [
  path.join(ROOT, 'artifacts/monitor/w4-status.json'),
  path.join(ROOT, 'artifacts/monitor/status.json'),
];

function readStatus() {
  for (const p of STATUS_PATHS) {
    try {
      if (fs.existsSync(p)) return JSON.parse(fs.readFileSync(p, 'utf8'));
    } catch (_) {}
  }
  return null;
}

function loadAlertsFromFs({ since, limit = 50 } = {}) {
  const sinceMs = since ? Date.parse(since) : 0;
  const files = fs.existsSync(ALERTS_DIR)
    ? fs.readdirSync(ALERTS_DIR).filter((f) => f.endsWith('.jsonl')).sort().reverse()
    : [];
  const alerts = [];
  for (const f of files) {
    const lines = fs.readFileSync(path.join(ALERTS_DIR, f), 'utf8').split('\n').filter(Boolean);
    for (let i = lines.length - 1; i >= 0; i--) {
      try {
        const o = JSON.parse(lines[i]);
        const ts = Date.parse(o.ts || o.timestamp || 0);
        if (sinceMs && ts && ts < sinceMs) continue;
        alerts.push(o);
        if (alerts.length >= limit) return alerts;
      } catch (_) {}
    }
  }
  return alerts;
}

function fsRecent(limit = 20) {
  const status = readStatus();
  const alerts = loadAlertsFromFs({ limit });
  return {
    alerts,
    count: alerts.length,
    alerts_dispatched: status ? Number(status.alerts_dispatched || 0) : alerts.length,
    anomaly_count: status ? Number(status.anomaly_count || 0) : null,
    backend: 'filesystem',
    upstream: MONITOR_BASE,
  };
}

async function getRecent(limit = 20) {
  const up = await tryUpstream(MONITOR_BASE, 'GET', '/alerts/recent', { query: { limit } });
  if (up.ok) return { ...(typeof up.data === 'object' ? up.data : { data: up.data }), backend: 'http' };
  return fsRecent(limit);
}

async function getSince(since, limit = 50) {
  const up = await tryUpstream(MONITOR_BASE, 'GET', '/alerts', { query: { since, limit } });
  if (up.ok) return { ...(typeof up.data === 'object' ? up.data : { data: up.data }), backend: 'http' };
  return {
    alerts: loadAlertsFromFs({ since, limit }),
    since: since || null,
    backend: 'filesystem',
    upstream: MONITOR_BASE,
  };
}

function alertCount() {
  const status = readStatus();
  if (status && status.alerts_dispatched != null) return Number(status.alerts_dispatched);
  return loadAlertsFromFs({ limit: 10000 }).length;
}

module.exports = { getRecent, getSince, alertCount, fsRecent, readStatus };
