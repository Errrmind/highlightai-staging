const counts = {
  http_requests_total: 0,
  by_route: {},
};

function metricsMiddleware(req, res, next) {
  counts.http_requests_total += 1;
  const key = `${req.method} ${req.path}`;
  counts.by_route[key] = (counts.by_route[key] || 0) + 1;
  const start = Date.now();
  res.on('finish', () => {
    counts.last_latency_ms = Date.now() - start;
  });
  next();
}

function renderPrometheus() {
  const lines = [
    '# HELP http_requests_total Total HTTP requests',
    '# TYPE http_requests_total counter',
    `http_requests_total ${counts.http_requests_total}`,
    '# HELP ha_orchestrator_up Orchestrator process up',
    '# TYPE ha_orchestrator_up gauge',
    'ha_orchestrator_up 1',
  ];
  for (const [route, n] of Object.entries(counts.by_route)) {
    const safe = route.replace(/"/g, '\\"');
    lines.push(`http_requests_by_route{route="${safe}"} ${n}`);
  }
  return lines.join('\n') + '\n';
}

module.exports = { metricsMiddleware, renderPrometheus, counts };
