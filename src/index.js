const express = require('express');
const cors = require('cors');
const path = require('path');
const { metricsMiddleware, renderPrometheus } = require('./middleware/metrics');
const { logSkill } = require('./lib/audit');
const tasksRouter = require('./routes/tasks');
const askRouter = require('./routes/ask');
const spaRouter = require('./routes/spa');
const humangateRouter = require('./routes/humangate');

const app = express();
const PORT = Number(process.env.PORT || 4310);

app.use(cors());
app.use(express.json({ limit: '2mb' }));
app.use(metricsMiddleware);

app.get('/health', (_req, res) => {
  res.json({ status: 'ok', bot: 'agent.orchestrator', task: 'CORE-BUILD-V1', project_id: 'highlightai-pending' });
});
app.get('/orchestrator/health', (_req, res) => {
  res.json({ status: 'ok', bot: 'agent.orchestrator', task: 'CORE-BUILD-V1', project_id: 'highlightai-pending' });
});
app.get('/metrics', (_req, res) => {
  res.type('text/plain').send(renderPrometheus());
});

app.use('/orchestrator', tasksRouter);
app.use('/orchestrator', askRouter);
app.use('/orchestrator', spaRouter);
app.use('/humangate', humangateRouter);

// Approvals SPA (W4-HUMANGATE)
const spaDist = path.join(__dirname, '..', 'spa', 'dist');
app.use('/approvals', express.static(spaDist));
app.get('/approvals/*', (_req, res) => {
  res.sendFile(path.join(spaDist, 'index.html'));
});

app.use(express.static(path.join(__dirname, '..', 'public')));

app.use((err, _req, res, _next) => {
  console.error(err);
  res.status(500).json({ error: 'internal', message: String(err.message || err) });
});

if (require.main === module) {
  const HOST = process.env.HOST || '0.0.0.0';
  app.listen(PORT, HOST, () => {
    logSkill('agent.orchestrator', 'server.start', { port: PORT, host: HOST });
    console.log(`HA orchestrator listening on http://${HOST}:${PORT}`);
  });
}

module.exports = app;
