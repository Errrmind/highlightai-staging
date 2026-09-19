const express = require('express');
const { logSkill } = require('../lib/audit');
const { queryMemory } = require('../lib/memoryClient');

const router = express.Router();

function streamAnswer(res, question, caller_id) {
  logSkill(caller_id || 'anonymous', 'ask.stream', { question: question.slice(0, 200) });
  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');
  res.flushHeaders?.();

  const { hits, production_ready } = queryMemory(question, { limit: 5 });
  const citations = hits.map((h) => ({
    record_id: h.record_id,
    snippet: h.text,
    score: h.score,
  }));

  const chunks = [
    'RAG step4 (local memory query, production_ready=' + production_ready + ')…\n',
    `Q: ${question}\n`,
    citations.length ? `Citations: ${citations.length} clear-path hit(s).\n` : 'No clear-path memory hits.\n',
    citations.length
      ? `Answer: Based on indexed clear-path content (${citations.map((c) => c.record_id).join(', ')}): ${citations[0].snippet}\n`
      : 'Answer: No clear-path corpus available yet for this query.\n',
  ];

  let i = 0;
  const tick = () => {
    if (i < chunks.length) {
      res.write(`event: chunk\ndata: ${JSON.stringify({ text: chunks[i] })}\n\n`);
      i += 1;
      setTimeout(tick, 30);
    } else {
      res.write(`event: done\ndata: ${JSON.stringify({ citations, task_id: 'CORE-BUILD-V1', production_ready })}\n\n`);
      res.end();
    }
  };
  tick();
}

router.post('/ask', (req, res) => {
  const question = (req.body && (req.body.question || req.body.q)) || '';
  if (!question) return res.status(400).json({ error: 'question required' });
  streamAnswer(res, question, req.headers['x-caller-id'] || req.user?.sub);
});

router.get('/ask/stream', (req, res) => {
  const question = req.query.q || req.query.question || '';
  if (!question) return res.status(400).json({ error: 'q required' });
  streamAnswer(res, String(question), req.headers['x-caller-id'] || 'anonymous');
});

module.exports = router;
