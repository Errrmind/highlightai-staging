const express = require('express');
const jwt = require('jsonwebtoken');
const { logSkill } = require('../lib/audit');

const router = express.Router();
const SECRET = process.env.ORCH_JWT_SECRET || 'dev-local-only';

router.post('/auth/session', (req, res) => {
  const sub = (req.body && req.body.user_id) || 'operator';
  const token = jwt.sign({ sub, project_id: 'highlightai-pending' }, SECRET, { expiresIn: '12h' });
  logSkill(sub, 'auth.session', {});
  res.json({ token, expires_in: 43200, token_type: 'Bearer' });
});

router.post('/search', (req, res) => {
  const q = (req.body && req.body.q) || '';
  logSkill(req.headers['x-caller-id'] || 'anonymous', 'search', { q: q.slice(0, 120) });
  res.json({ query: q, results: [], note: 'W2 memory RAG pending' });
});

router.post('/annotations', (req, res) => {
  logSkill(req.headers['x-caller-id'] || 'anonymous', 'annotations.create', {});
  res.status(201).json({ id: `ann_${Date.now()}`, ...(req.body || {}) });
});

router.post('/feedback', (req, res) => {
  logSkill(req.headers['x-caller-id'] || 'anonymous', 'feedback.create', {});
  res.status(201).json({ ok: true, ...(req.body || {}) });
});

module.exports = router;
