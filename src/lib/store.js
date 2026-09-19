const { v4: uuid } = require('uuid');
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
  return { total: all.length, items: all.slice(offset, offset + limit) };
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

module.exports = { createTask, listTasks, getTask, assignSubtasks, MAX_PARALLEL, tasks };
