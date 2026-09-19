const fs = require('fs');
const path = require('path');
const { AUDIT_SKILLS, AUDIT_GATES } = require('./paths');

function appendJsonl(file, obj) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.appendFileSync(file, JSON.stringify({ ...obj, ts: obj.ts || new Date().toISOString() }) + '\n');
}

function logSkill(caller_id, skill, extra = {}) {
  appendJsonl(AUDIT_SKILLS, { skill, caller_id, task_id: 'CORE-BUILD-V1', ...extra });
}

function openGate({ condition, bot_id, summary, artifact_paths = [], project_id = 'highlightai-pending' }) {
  const gate = {
    gate_id: `gate_${Date.now()}`,
    bot_id,
    condition,
    evidence: { summary, artifact_paths },
    opened_at: new Date().toISOString(),
    project_id,
    task_id: 'CORE-BUILD-V1',
    required_approvals: 1,
    channels: ['ui'],
  };
  appendJsonl(AUDIT_GATES, gate);
  logSkill('agent.orchestrator', 'gate.open', { condition, gate_id: gate.gate_id });
  return gate;
}

module.exports = { logSkill, openGate, appendJsonl };
