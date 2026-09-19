/**
 * Humangate mount for Approvals SPA.
 * - If HUMANGATE_URL set: proxy to upstream
 * - Else: filesystem adapter over services/humangate/state
 * Never auto-approves. Reject requires comment.
 */
const express = require('express');
const fs = require('fs');
const path = require('path');
const http = require('http');
const https = require('https');
const { URL } = require('url');

const router = express.Router();

const STATE_ROOT =
  process.env.HUMANGATE_STATE_ROOT ||
  path.resolve(__dirname, '../../../humangate/state');
const AUDIT =
  process.env.HUMANGATE_AUDIT ||
  path.resolve(__dirname, '../../../../audit/gates.jsonl');

const BUCKETS = ['pending', 'approved', 'rejected', 'escalated'];

function ensure() {
  for (const b of BUCKETS) {
    fs.mkdirSync(path.join(STATE_ROOT, b), { recursive: true });
  }
}

function readJson(file) {
  return JSON.parse(fs.readFileSync(file, 'utf8'));
}

function writeJson(file, obj) {
  fs.writeFileSync(file, JSON.stringify(obj, null, 2) + '\n');
}

function listBucket(name) {
  const dir = path.join(STATE_ROOT, name);
  if (!fs.existsSync(dir)) return [];
  return fs
    .readdirSync(dir)
    .filter((f) => f.endsWith('.json'))
    .map((f) => {
      try {
        return readJson(path.join(dir, f));
      } catch {
        return null;
      }
    })
    .filter(Boolean);
}

function findGate(id) {
  for (const b of BUCKETS) {
    const file = path.join(STATE_ROOT, b, `${id}.json`);
    if (fs.existsSync(file)) return { gate: readJson(file), bucket: b, file };
  }
  // prefix match
  for (const b of BUCKETS) {
    const dir = path.join(STATE_ROOT, b);
    if (!fs.existsSync(dir)) continue;
    for (const f of fs.readdirSync(dir)) {
      if (f.startsWith(id) && f.endsWith('.json')) {
        const file = path.join(dir, f);
        return { gate: readJson(file), bucket: b, file };
      }
    }
  }
  return null;
}

function audit(type, payload) {
  try {
    fs.mkdirSync(path.dirname(AUDIT), { recursive: true });
    fs.appendFileSync(
      AUDIT,
      JSON.stringify({ ts: new Date().toISOString(), bot: 'agent.humangate', type, ...payload }) +
        '\n'
    );
  } catch (e) {
    console.error('audit fail', e.message);
  }
}

function moveTo(found, bucket, gate) {
  const dest = path.join(STATE_ROOT, bucket, path.basename(found.file));
  writeJson(dest, gate);
  if (found.file !== dest && fs.existsSync(found.file)) fs.unlinkSync(found.file);
}

function proxyToUpstream(req, res) {
  const base = process.env.HUMANGATE_URL;
  if (!base) return false;
  try {
    const u = new URL(req.originalUrl.replace(/^\/humangate/, '') || '/', base);
    if (!u.pathname.startsWith('/humangate')) {
      u.pathname = '/humangate' + (u.pathname === '/' ? '' : u.pathname);
    }
    const lib = u.protocol === 'https:' ? https : http;
    const headers = { ...req.headers, host: u.host };
    delete headers['content-length'];
    const preq = lib.request(
      u,
      { method: req.method, headers },
      (pres) => {
        res.writeHead(pres.statusCode || 502, pres.headers);
        pres.pipe(res);
      }
    );
    preq.on('error', (e) => res.status(502).json({ error: 'upstream', message: e.message }));
    if (req.method !== 'GET' && req.method !== 'HEAD') {
      preq.write(JSON.stringify(req.body || {}));
    }
    preq.end();
    return true;
  } catch (e) {
    res.status(502).json({ error: 'proxy', message: e.message });
    return true;
  }
}

router.use((req, res, next) => {
  if (process.env.HUMANGATE_URL) {
    if (proxyToUpstream(req, res)) return;
  }
  next();
});

router.get('/', (_req, res) => {
  ensure();
  const pending = listBucket('pending');
  res.json({
    service: 'humangate',
    bot: 'agent.humangate',
    status: 'ready',
    mode: process.env.HUMANGATE_URL ? 'proxy' : 'filesystem',
    pending_count: pending.length,
    auto_approve: false,
    sole_approver: 'TlAB',
    endpoints: ['/humangate/health', '/humangate/gates', '/approvals'],
  });
});

router.get('/health', (_req, res) => {
  ensure();
  const pending = listBucket('pending');
  res.json({
    service: 'humangate',
    bot: 'agent.humangate',
    status: 'ready',
    mode: process.env.HUMANGATE_URL ? 'proxy' : 'filesystem',
    pending_count: pending.length,
    auto_approve: false,
    sole_approver: 'TlAB',
    live_orch: 'https://orchestrator-production-7346.up.railway.app',
  });
});

router.get('/gates', (_req, res) => {
  ensure();
  res.json({
    pending: listBucket('pending'),
    approved: listBucket('approved'),
    rejected: listBucket('rejected'),
    escalated: listBucket('escalated'),
    pending_count: listBucket('pending').length,
    max_pending: 50,
    auto_approve: false,
  });
});

router.get('/gates/:id', (req, res) => {
  const found = findGate(req.params.id);
  if (!found) return res.status(404).json({ error: 'gate not found' });
  res.json(found.gate);
});

router.post('/gates/:id/approve', (req, res) => {
  const found = findGate(req.params.id);
  if (!found) return res.status(404).json({ error: 'gate not found' });
  if (found.bucket !== 'pending') {
    return res.status(409).json({ error: `gate is ${found.bucket}` });
  }
  const approver_id = req.body?.approver_id || req.body?.approver || 'TlAB';
  const comment = req.body?.comment || null;
  const gate = found.gate;
  gate.approvals = gate.approvals || [];
  gate.approvals.push({ approver_id, comment, at: new Date().toISOString() });
  const need = gate.required_approvals || gate.required_approvals || 1;
  if (gate.approvals.length >= need) {
    gate.status = 'approved';
    gate.resolved_at = new Date().toISOString();
    gate.resolve_reason = comment || 'quorum reached';
    moveTo(found, 'approved', gate);
    audit('gate.approved', { gate_id: gate.id || gate.gate_id, approver_id });
  } else {
    gate.updated_at = new Date().toISOString();
    writeJson(found.file, gate);
    audit('gate.partial_approve', { gate_id: gate.id || gate.gate_id, approver_id });
  }
  res.json(gate);
});

router.post('/gates/:id/reject', (req, res) => {
  const comment = req.body?.comment;
  if (typeof comment !== 'string' || !comment.trim()) {
    return res.status(400).json({ error: 'comment (reject rationale) is required', status: 400 });
  }
  const found = findGate(req.params.id);
  if (!found) return res.status(404).json({ error: 'gate not found' });
  if (found.bucket !== 'pending') {
    return res.status(409).json({ error: `gate is ${found.bucket}` });
  }
  const approver_id = req.body?.approver_id || req.body?.approver || 'TlAB';
  const gate = found.gate;
  gate.rejections = gate.rejections || [];
  gate.rejections.push({ approver_id, comment, at: new Date().toISOString() });
  gate.status = 'rejected';
  gate.resolved_at = new Date().toISOString();
  gate.resolve_reason = comment;
  moveTo(found, 'rejected', gate);
  audit('gate.rejected', { gate_id: gate.id || gate.gate_id, approver_id });
  res.json(gate);
});

router.post('/gates/:id/more-info', (req, res) => {
  const comment = req.body?.comment;
  if (typeof comment !== 'string' || !comment.trim()) {
    return res.status(400).json({ error: 'comment is required', status: 400 });
  }
  const found = findGate(req.params.id);
  if (!found) return res.status(404).json({ error: 'gate not found' });
  if (found.bucket !== 'pending') {
    return res.status(409).json({ error: `gate is ${found.bucket}` });
  }
  const approver_id = req.body?.approver_id || req.body?.approver || 'TlAB';
  const gate = found.gate;
  gate.more_info_requests = gate.more_info_requests || [];
  gate.more_info_requests.push({ approver_id, comment, at: new Date().toISOString() });
  gate.updated_at = new Date().toISOString();
  writeJson(found.file, gate);
  audit('gate.more_info', { gate_id: gate.id || gate.gate_id, approver_id });
  res.json(gate);
});

module.exports = router;
