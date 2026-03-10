const http = require('http');
const fs = require('fs');
const path = require('path');

function createServer({ config, logger }) {
  const router = [];
  require('../interfaces/client_bot').registerClientBotRoutes(router);
  require('../interfaces/master_bot').registerMasterBotRoutes(router);
  require('../interfaces/integration_bot').registerIntegrationBotRoutes(router);

  return http.createServer((req, res) => {
    if (req.url === '/health') {
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ ok: true, env: config.nodeEnv }));
      return;
    }


    if (req.url === '/styles.css' || req.url === '/webapp.js') {
      const staticPath = path.join(process.cwd(), 'public', req.url.slice(1));
      const content = fs.readFileSync(staticPath, 'utf8');
      const contentType = req.url.endsWith('.css') ? 'text/css' : 'application/javascript';
      res.writeHead(200, { 'Content-Type': contentType + '; charset=utf-8' });
      res.end(content);
      return;
    }

    if (req.url === '/' || req.url.startsWith('/forms') || req.url === '/requests' || req.url === '/recommendations') {
      const htmlPath = path.join(process.cwd(), 'public', 'index.html');
      const html = fs.readFileSync(htmlPath, 'utf8');
      res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
      res.end(html);
      return;
    }

    const matched = router.find((item) => item.path === req.url && item.method === req.method);
    if (matched) {
      logger.info(`Accepted webhook route: ${req.method} ${req.url}`);
      res.writeHead(202, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ accepted: true }));
      return;
    }

    res.writeHead(404, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ error: 'Not found' }));
  });
}

module.exports = { createServer };
