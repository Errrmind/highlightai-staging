const http = require('http');
const https = require('https');
const { URL } = require('url');

const MEMORY_BASE = process.env.MEMORY_BASE_URL || process.env.HA_MEMORY_URL || 'http://127.0.0.1:8092';
const MONITOR_BASE = process.env.MONITOR_BASE_URL || process.env.HA_MONITOR_URL || 'http://127.0.0.1:8093';

function requestJson(base, method, pathname, { query, body, timeoutMs = 2500 } = {}) {
  return new Promise((resolve, reject) => {
    let u;
    try {
      u = new URL(pathname, base.endsWith('/') ? base : base + '/');
    } catch (e) {
      return reject(e);
    }
    if (query) {
      for (const [k, v] of Object.entries(query)) {
        if (v != null && v !== '') u.searchParams.set(k, String(v));
      }
    }
    const lib = u.protocol === 'https:' ? https : http;
    const payload = body != null ? JSON.stringify(body) : null;
    const req = lib.request(
      {
        protocol: u.protocol,
        hostname: u.hostname,
        port: u.port || (u.protocol === 'https:' ? 443 : 80),
        path: u.pathname + u.search,
        method,
        headers: {
          Accept: 'application/json',
          ...(payload ? { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(payload) } : {}),
        },
        timeout: timeoutMs,
      },
      (res) => {
        const chunks = [];
        res.on('data', (c) => chunks.push(c));
        res.on('end', () => {
          const raw = Buffer.concat(chunks).toString('utf8');
          let data = raw;
          try { data = raw ? JSON.parse(raw) : null; } catch (_) {}
          resolve({ ok: res.statusCode >= 200 && res.statusCode < 300, status: res.statusCode, data, backend: 'http' });
        });
      }
    );
    req.on('timeout', () => { req.destroy(new Error('upstream timeout')); });
    req.on('error', reject);
    if (payload) req.write(payload);
    req.end();
  });
}

async function tryUpstream(base, method, pathname, opts) {
  try {
    return await requestJson(base, method, pathname, opts);
  } catch (e) {
    return { ok: false, status: 0, error: e.message, backend: 'http-failed' };
  }
}

module.exports = { MEMORY_BASE, MONITOR_BASE, tryUpstream, requestJson };
