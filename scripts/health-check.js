const http = require('http');
const port = process.env.PORT || 4310;
http.get(`http://127.0.0.1:${port}/orchestrator/health`, (res) => {
  let d = '';
  res.on('data', (c) => (d += c));
  res.on('end', () => {
    console.log(res.statusCode, d);
    process.exit(res.statusCode === 200 ? 0 : 1);
  });
}).on('error', (e) => {
  console.error(e.message);
  process.exit(1);
});
