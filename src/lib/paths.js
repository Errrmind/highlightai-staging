const path = require('path');
const ROOT = process.env.HA_ROOT || '/workspace/highlightai';
module.exports = {
  ROOT,
  AUDIT_SKILLS: path.join(ROOT, 'audit/orchestrator-skills.jsonl'),
  AUDIT_GATES: path.join(ROOT, 'audit/gates.jsonl'),
  MEMORY_ART: path.join(ROOT, 'artifacts/memory'),
  ORCH_STATUS: path.join(ROOT, 'artifacts/orchestrator/STATUS.md'),
  WAVE1: path.join(ROOT, 'artifacts/orchestrator/tasks/CORE-BUILD-V1/wave1.json'),
};
