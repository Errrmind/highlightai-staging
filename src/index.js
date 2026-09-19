const express = require('express');
const cors = require('cors');
const path = require('path');
const { metricsMiddleware, renderPrometheus } = require('./middleware/metrics');
const { logSkill } = require('./lib/audit');
const tasksRouter = require('./routes/tasks');
const askRouter = require('./routes/ask');
const spaRouter = require('./routes/spa');

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

app.use(express.static(path.join(__dirname, '..', 'public')));

app.use((err, _req, res, _next) => {
  console.error(err);
  res.status(500).json({ error: 'internal', message: String(err.message || err) });
});

if (require.main === module) {
  app.listen(PORT, '127.0.0.1', () => {
    logSkill('agent.orchestrator', 'server.start', { port: PORT });
    console.log(`HA orchestrator listening on http://127.0.0.1:${PORT}`);
  });
}

module.exports = app;
