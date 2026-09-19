const fs = require('fs');
const path = require('path');
const { MEMORY_ART } = require('./paths');

/** Local filesystem stand-in for GET/POST /memory/query (clear-path only). */
function queryMemory(question, { limit = 5 } = {}) {
  const hits = [];
  const chunksPath = path.join(MEMORY_ART, 'store/chunks.jsonl');
  if (!fs.existsSync(chunksPath)) return { hits, production_ready: false };
  const q = String(question || '').toLowerCase();
  const lines = fs.readFileSync(chunksPath, 'utf8').split('\n').filter(Boolean);
  for (const line of lines) {
    let o;
    try { o = JSON.parse(line); } catch { continue; }
    // exclude gated lineages if metadata present
    const batch = (o.metadata && o.metadata.provenance && o.metadata.provenance.batch_id) || '';
    if (batch === 'batch-002' || batch === 'batch-003') continue;
    if (o.record_id === 'ha-e9572b47baa503c3a27872fc') continue;
    const text = o.text || '';
    const score = q.split(/\s+/).filter(Boolean).reduce((s, w) => s + (text.toLowerCase().includes(w) ? 1 : 0), 0);
    hits.push({ record_id: o.record_id, chunk_id: o.chunk_id, text: text.slice(0, 240), score, path: chunksPath });
  }
  hits.sort((a, b) => b.score - a.score);
  return { hits: hits.slice(0, limit), production_ready: false, backend: 'filesystem-chunks' };
}

module.exports = { queryMemory };
