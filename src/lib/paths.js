const fs = require('fs');
const path = require('path');

/** Root for HighlightAI filesystem contracts. Railway: set HA_ROOT=/data/highlightai */
const ROOT =
  process.env.HA_ROOT ||
  (fs.existsSync('/workspace/highlightai')
    ? '/workspace/highlightai'
    : path.join(__dirname, '..', '..', 'data'));

const AUDIT_SKILLS = path.join(ROOT, 'audit/orchestrator-skills.jsonl');
const AUDIT_GATES = path.join(ROOT, 'audit/gates.jsonl');
const MEMORY_ART = path.join(ROOT, 'artifacts/memory');
const ORCH_STATUS = path.join(ROOT, 'artifacts/orchestrator/STATUS.md');
const WAVE1 = path.join(ROOT, 'artifacts/orchestrator/tasks/CORE-BUILD-V1/wave1.json');

function ensureParent(filePath) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
}

module.exports = {
  ROOT,
  AUDIT_SKILLS,
  AUDIT_GATES,
  MEMORY_ART,
  ORCH_STATUS,
  WAVE1,
  ensureParent,
};
