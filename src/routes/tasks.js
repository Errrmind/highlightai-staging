const express = require('express');
const { createTask, listTasks, getTask, assignSubtasks, MAX_PARALLEL } = require('../lib/store');
const { logSkill, openGate } = require('../lib/audit');

const router = express.Router();

router.post('/tasks', (req, res) => {
  const task = createTask(req.body || {});
  logSkill(req.headers['x-caller-id'] || 'agent.orchestrator', 'tasks.create', { task_id: task.id });
  res.status(201).json(task);
});

router.get('/tasks', (req, res) => {
  const { project_id, status, limit, offset } = req.query;
  res.json(listTasks({
    project_id,
    status,
    limit: limit ? Number(limit) : 20,
    offset: offset ? Number(offset) : 0,
  }));
});

router.get('/tasks/:taskId', (req, res) => {
  const task = getTask(req.params.taskId);
  if (!task) return res.status(404).json({ error: 'not found' });
  res.json(task);
});

router.get('/tasks/:taskId/status', (req, res) => {
  const task = getTask(req.params.taskId);
  if (!task) return res.status(404).json({ error: 'not found' });
  res.json({
    id: task.id,
    status: task.status,
    subtasks: task.subtasks.map((s) => ({ id: s.subtask_id, bot: s.bot, status: s.status })),
    max_parallel: task.max_parallel,
  });
});

router.post('/tasks/:taskId/assign', (req, res) => {
  try {
    const task = assignSubtasks(req.params.taskId, (req.body && req.body.subtasks) || []);
    if (!task) return res.status(404).json({ error: 'not found' });
    logSkill(req.headers['x-caller-id'] || 'agent.orchestrator', 'tasks.assign', {
      task_id: task.id,
      count: task.subtasks.length,
    });
    res.json(task);
  } catch (e) {
    if (e.code === 'MAX_PARALLEL') return res.status(400).json({ error: e.message, max_parallel: MAX_PARALLEL });
    throw e;
  }
});

router.post('/gates', (req, res) => {
  const { condition, bot_id, summary, artifact_paths } = req.body || {};
  if (!condition || !bot_id || !summary) {
    return res.status(400).json({ error: 'condition, bot_id, summary required' });
  }
  const allowed = ['anonymize_false', 'license_ambiguous', 'pii_detected', 'security_critical', 'deploy_blocked', 'manual'];
  if (!allowed.includes(condition)) return res.status(400).json({ error: 'invalid condition' });
  const gate = openGate({ condition, bot_id, summary, artifact_paths });
  res.status(201).json(gate);
});

module.exports = router;
