const fs = require('fs');
const path = require('path');
const { MEMORY_ART } = require('./paths');
const { MEMORY_BASE, tryUpstream } = require('./upstream');

function readJsonSafe(p, fallback = null) {
  try {
    if (!fs.existsSync(p)) return fallback;
    return JSON.parse(fs.readFileSync(p, 'utf8'));
  } catch {
    return fallback;
  }
}

function fsStats() {
  const health = readJsonSafe(path.join(MEMORY_ART, 'health.json'), {});
  const w2 = readJsonSafe(path.join(MEMORY_ART, 'W2-MEMORY-STATUS.json'), {});
  const ingest = readJsonSafe(path.join(MEMORY_ART, 'local-ingest-status.json'), {});
  const chunksPath = path.join(MEMORY_ART, 'store/chunks.jsonl');
  let chunk_count = 0;
  if (fs.existsSync(chunksPath)) {
    chunk_count = fs.readFileSync(chunksPath, 'utf8').split('\n').filter(Boolean).length;
  }
  const production_ready = !!(w2.production_ready || ingest.production_ready || false);
  return {
    service: 'agent.memory',
    production_ready,
    mode: health.mode || w2.mode || 'filesystem-local',
    project_id: health.project_id || w2.project_id || 'highlightai-pending',
    chunk_count,
    records_accepted: w2.records_accepted ?? ingest.records_ingested ?? null,
    index_chunks: w2.index_chunks ?? chunk_count,
    blocked_batches: w2.blocked_batches || ['002', '003'],
    health,
    w2_status: { production_ready, records_accepted: w2.records_accepted, index_chunks: w2.index_chunks },
    backend: 'filesystem',
    upstream: MEMORY_BASE,
  };
}

function fsChunk(id) {
  const chunksPath = path.join(MEMORY_ART, 'store/chunks.jsonl');
  if (!fs.existsSync(chunksPath)) return null;
  for (const line of fs.readFileSync(chunksPath, 'utf8').split('\n').filter(Boolean)) {
    try {
      const o = JSON.parse(line);
      if (o.chunk_id === id || o.record_id === id || o.id === id) return o;
    } catch (_) {}
  }
  return null;
}

function fsExport({ limit = 100 } = {}) {
  const chunksPath = path.join(MEMORY_ART, 'store/chunks.jsonl');
  const out = [];
  if (!fs.existsSync(chunksPath)) return { chunks: out, backend: 'filesystem' };
  for (const line of fs.readFileSync(chunksPath, 'utf8').split('\n').filter(Boolean)) {
    try {
      const o = JSON.parse(line);
      const batch = (o.metadata && o.metadata.provenance && o.metadata.provenance.batch_id) || '';
      if (batch === 'batch-002' || batch === 'batch-003') continue;
      if (o.record_id === 'ha-e9572b47baa503c3a27872fc') continue;
      out.push(o);
      if (out.length >= limit) break;
    } catch (_) {}
  }
  return { chunks: out, count: out.length, clear_path_only: true, backend: 'filesystem' };
}

async function getStats() {
  const up = await tryUpstream(MEMORY_BASE, 'GET', '/memory/stats');
  if (up.ok) return { ...up.data, backend: 'http', upstream: MEMORY_BASE };
  return fsStats();
}

async function getChunk(id) {
  const up = await tryUpstream(MEMORY_BASE, 'GET', `/memory/chunk/${encodeURIComponent(id)}`);
  if (up.ok) return { ...((typeof up.data === 'object' && up.data) || { data: up.data }), backend: 'http' };
  const hit = fsChunk(id);
  if (!hit) return null;
  return { ...hit, backend: 'filesystem' };
}

async function exportChunks(opts) {
  const up = await tryUpstream(MEMORY_BASE, 'GET', '/memory/export', { query: opts });
  if (up.ok) return { ...(typeof up.data === 'object' ? up.data : { data: up.data }), backend: 'http' };
  const up2 = await tryUpstream(MEMORY_BASE, 'POST', '/memory/export', { body: opts || {} });
  if (up2.ok) return { ...(typeof up2.data === 'object' ? up2.data : { data: up2.data }), backend: 'http' };
  return fsExport(opts);
}

module.exports = { getStats, getChunk, exportChunks, fsStats };
