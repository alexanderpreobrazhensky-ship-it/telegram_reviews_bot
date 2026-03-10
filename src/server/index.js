const http = require('http');
const fs = require('fs');
const path = require('path');
const { URL } = require('url');
const db = require('../infrastructure/db');
const { REQUEST_TYPES } = require('../core/domain');

function readBody(req) {
  return new Promise((resolve) => {
    let raw = '';
    req.on('data', (chunk) => {
      raw += chunk;
    });
    req.on('end', () => {
      if (!raw) return resolve({});
      try {
        resolve(JSON.parse(raw));
      } catch {
        resolve({});
      }
    });
  });
}

function sendJson(res, status, payload) {
  res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8' });
  res.end(JSON.stringify(payload));
}

function serveFile(res, filePath, contentType) {
  const content = fs.readFileSync(filePath, 'utf8');
  res.writeHead(200, { 'Content-Type': `${contentType}; charset=utf-8` });
  res.end(content);
}

function createClientRequest({ body, type, sourceChannel = 'webapp' }) {
  const client = db.upsertClient({ fullName: body.fullName, phone: body.phone, telegramId: body.telegramId ? String(body.telegramId) : null });
  const vehicle = db.upsertVehicle({
    clientId: client.id,
    brand: body.brand,
    model: body.model,
    year: body.year,
    vin: body.vin,
    plateNumber: body.plateNumber
  });
  const request = db.createRequest({ clientId: client.id, vehicleId: vehicle?.id || null, requestType: type, description: body.description || body.question || body.changeDetails || '', sourceChannel });
  db.createCommunicationEvent({ clientId: client.id, requestId: request.id, source: sourceChannel === 'webapp' ? 'webapp' : 'bot', payload: { action: 'request_created', type } });
  return { client, vehicle, request };
}

function createServer({ config, logger }) {
  const router = [];
  require('../interfaces/client_bot').registerClientBotRoutes(router);
  require('../interfaces/master_bot').registerMasterBotRoutes(router);
  require('../interfaces/integration_bot').registerIntegrationBotRoutes(router);

  return http.createServer(async (req, res) => {
    const requestUrl = new URL(req.url, 'http://localhost');
    const pathname = requestUrl.pathname;

    if (req.method === 'GET' && pathname === '/health') return sendJson(res, 200, { ok: true, env: config.nodeEnv });

    if (req.method === 'GET' && (pathname === '/styles.css' || pathname === '/webapp.js')) {
      const staticPath = path.join(process.cwd(), 'public', pathname.slice(1));
      return serveFile(res, staticPath, pathname.endsWith('.css') ? 'text/css' : 'application/javascript');
    }

    const webPages = ['/', '/requests', '/recommendations', '/forms/service-request', '/forms/parts-request', '/forms/consultation', '/forms/warranty-request', '/forms/data-change-request'];
    if (req.method === 'GET' && webPages.includes(pathname)) {
      return serveFile(res, path.join(process.cwd(), 'public', 'index.html'), 'text/html');
    }

    if (req.method === 'POST' && pathname === '/api/client/requests/service') return sendJson(res, 201, createClientRequest({ body: await readBody(req), type: REQUEST_TYPES.SERVICE }).request);
    if (req.method === 'POST' && pathname === '/api/client/requests/parts') return sendJson(res, 201, createClientRequest({ body: await readBody(req), type: REQUEST_TYPES.PARTS }).request);
    if (req.method === 'POST' && pathname === '/api/client/requests/consultation') return sendJson(res, 201, createClientRequest({ body: await readBody(req), type: REQUEST_TYPES.CONSULTATION }).request);
    if (req.method === 'POST' && pathname === '/api/client/requests/warranty') return sendJson(res, 201, createClientRequest({ body: await readBody(req), type: REQUEST_TYPES.WARRANTY }).request);
    if (req.method === 'POST' && pathname === '/api/client/requests/data-change') return sendJson(res, 201, createClientRequest({ body: await readBody(req), type: REQUEST_TYPES.DATA_CHANGE }).request);

    if (req.method === 'GET' && pathname === '/api/client/requests') {
      return sendJson(res, 200, { items: db.listRequests({ phone: requestUrl.searchParams.get('phone'), telegramId: requestUrl.searchParams.get('telegramId') }) });
    }

    if (req.method === 'GET' && pathname === '/api/client/recommendations') {
      return sendJson(res, 200, { items: db.listRecommendations({ phone: requestUrl.searchParams.get('phone'), telegramId: requestUrl.searchParams.get('telegramId') }) });
    }

    if (req.method === 'POST' && pathname.startsWith('/api/client/recommendations/') && pathname.endsWith('/interest')) {
      const id = pathname.split('/')[4];
      const updated = db.markRecommendationInterest(id);
      return updated ? sendJson(res, 200, updated) : sendJson(res, 404, { error: 'Not found' });
    }

    const matched = router.find((item) => item.path === pathname && item.method === req.method);
    if (matched) {
      const body = await readBody(req);
      const payload = matched.handler ? await matched.handler({ body, config }) : { accepted: true };
      logger.info(`Accepted route: ${req.method} ${pathname}`);
      return sendJson(res, 200, payload);
    }

    return sendJson(res, 404, { error: 'Not found' });
  });
}

module.exports = { createServer };
