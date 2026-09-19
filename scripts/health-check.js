const http = require('http');
const port = process.env.PORT || 4310;
const host = process.env.HEALTH_HOST || '127.0.0.1';
const req = http.get({ host, port, path: '/health', timeout: 4000 }, (res) => {
  process.exit(res.statusCode === 200 ? 0 : 1);
});
req.on('error', () => process.exit(1));
req.on('timeout', () => {
  req.destroy();
  process.exit(1);
});
