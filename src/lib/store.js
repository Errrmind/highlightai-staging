const { v4: uuid } = require('uuid');
const { evaluatePipelineHealth, rankTask, softCheckHandOff } = require('./bottleneck');
const MAX_PARALLEL = 8;
const tasks = new Map();

function createTask(body) {
  const id = body.task_id || `task_${uuid().slice(0, 8)}`;
  const task = {
    id,
    project_id: body.project_id || 'highlightai-pending',
    title: body.title || id,
    description: body.description || '',
    status: 'pending',
    capability_tags: body.capability_tags || [],
    max_parallel: Math.min(body.max_parallel || MAX_PARALLEL, MAX_PARALLEL),
    subtasks: [],
    created_at: new Date().toISOString(),
    payload: body.payload || {},
  };
  tasks.set(id, task);
  return task;
}

function listTasks({ project_id, status, limit = 20, offset = 0 } = {}) {
  let all = [...tasks.values()];
  if (project_id) all = all.filter((t) => t.project_id === project_id);
  if (status) all = all.filter((t) => t.status === status);
  const health = evaluatePipelineHealth();
  all = all
    .map((t) => ({ ...t, queue_score: rankTask(t, health) }))
    .sort((a, b) => (b.queue_score || 0) - (a.queue_score || 0));
  return { total: all.length, items: all.slice(offset, offset + limit), pipeline_health: health };
}

function getTask(id) {
  return tasks.get(id) || null;
}

function assignSubtasks(taskId, subtasks) {
  const task = tasks.get(taskId);
  if (!task) return null;
  if (!Array.isArray(subtasks)) throw new Error('subtasks required');
  if (subtasks.length > task.max_parallel) {
    const err = new Error(`max_parallel ${task.max_parallel} exceeded`);
    err.code = 'MAX_PARALLEL';
    throw err;
  }
  const health = evaluatePipelineHealth();
  for (const s of subtasks) {
    const bot = String(s.bot || '');
    const stage = bot.includes('formatter') ? 'formatter' : bot.includes('executor') ? 'executor' : null;
    if (stage) {
      const chk = softCheckHandOff(stage, health);
      if (!chk.ok) {
        const err = new Error(`hand-off blocked: ${chk.reason}`);
        err.code = 'SOFT_BOTTLENECK';
        err.health = chk.health;
        throw err;
      }
      s.pipeline_soft_warn = chk.soft_warn || false;
      s.pipeline_health = { bottleneck: health.bottleneck, p99_gap: health.p99_gap, ranking_adjust: health.ranking_adjust };
    }
  }
  task.subtasks = subtasks.map((s, i) => ({
    subtask_id: s.subtask_id || `st_${i + 1}`,
    bot: s.bot,
    capability_tags: s.capability_tags || [],
    status: 'assigned',
    ...s,
  }));
  task.status = 'running';
  return task;
}

module.exports = { createTask, listTasks, getTask, assignSubtasks, MAX_PARALLEL, tasks, evaluatePipelineHealth, rankTask, softCheckHandOff };
