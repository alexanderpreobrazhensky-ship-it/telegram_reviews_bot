const http = require('http');
const fs = require('fs');
const path = require('path');
const { URL } = require('url');
const db = require('../infrastructure/db');
const { REQUEST_TYPES } = require('../core/domain');
const { ingestEmail } = require('../integrations/email');
const { oneCSyncPlaceholder } = require('../integrations/one_c');
const { integrationService, createReportingService } = require('../core/application');

function readBody(req) {
  return new Promise((resolve) => {
    let raw = '';
    req.on('data', (chunk) => {
      raw += chunk;
    });
    req.on('end', () => {
      if (!raw) return resolve({ body: {}, invalidJson: false });
      try {
        resolve({ body: JSON.parse(raw), invalidJson: false });
      } catch {
        resolve({ body: {}, invalidJson: true });
      }
    });
  });
}

function sendJson(res, status, payload) {
  res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8' });
  res.end(JSON.stringify(payload));
}

function serveFile(res, filePath, contentType) {
  try {
    const content = fs.readFileSync(filePath, 'utf8');
    res.writeHead(200, { 'Content-Type': `${contentType}; charset=utf-8` });
    res.end(content);
  } catch {
    sendJson(res, 404, { error: 'Not found' });
  }
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


function validateClientRequestPayload(body = {}) {
  const errors = [];
  if (!String(body.fullName || '').trim()) errors.push('fullName is required');
  if (!String(body.phone || '').trim()) errors.push('phone is required');
  return errors;
}

function createServer({ config, logger }) {
  const router = [];
  const reportingService = createReportingService({ db });
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

    if (req.method === 'POST' && pathname.startsWith('/api/client/requests/')) {
      const { body, invalidJson } = await readBody(req);
      if (invalidJson) return sendJson(res, 400, { error: 'Invalid JSON payload' });
      const errors = validateClientRequestPayload(body);
      if (errors.length) return sendJson(res, 400, { error: 'Validation error', details: errors });

      const typeMap = {
        '/api/client/requests/service': REQUEST_TYPES.SERVICE,
        '/api/client/requests/parts': REQUEST_TYPES.PARTS,
        '/api/client/requests/consultation': REQUEST_TYPES.CONSULTATION,
        '/api/client/requests/warranty': REQUEST_TYPES.WARRANTY,
        '/api/client/requests/data-change': REQUEST_TYPES.DATA_CHANGE
      };
      const type = typeMap[pathname];
      if (!type) return sendJson(res, 404, { error: 'Not found' });
      return sendJson(res, 201, createClientRequest({ body, type }).request);
    }

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

    if (req.method === 'POST' && pathname === '/api/integrations/email') {
      const { body, invalidJson } = await readBody(req);
      if (invalidJson) return sendJson(res, 400, { error: 'Invalid JSON payload' });
      const event = ingestEmail(body);
      return sendJson(res, 201, event);
    }

    if (req.method === 'POST' && pathname === '/api/integrations/manual') {
      const { body, invalidJson } = await readBody(req);
      if (invalidJson) return sendJson(res, 400, { error: 'Invalid JSON payload' });
      const event = integrationService.receiveIntegrationEvent({
        sourceSystem: body.sourceSystem || integrationService.INTEGRATION_SOURCES.MANUAL_IMPORT,
        eventType: body.eventType || integrationService.INTEGRATION_EVENT_TYPES.MANUAL_REQUEST_IMPORT,
        rawPayload: body.rawPayload || body,
        dedupeKey: body.dedupeKey || null
      });
      return sendJson(res, 201, event);
    }

    if (req.method === 'POST' && pathname.startsWith('/api/integrations/one-c/')) {
      const { body, invalidJson } = await readBody(req);
      if (invalidJson) return sendJson(res, 400, { error: 'Invalid JSON payload' });
      const entityType = pathname.split('/')[4];
      const eventTypeMap = {
        client: integrationService.INTEGRATION_EVENT_TYPES.ONE_C_CLIENT_SYNC,
        vehicle: integrationService.INTEGRATION_EVENT_TYPES.ONE_C_VEHICLE_SYNC,
        visit: integrationService.INTEGRATION_EVENT_TYPES.ONE_C_VISIT_SYNC,
        recommendation: integrationService.INTEGRATION_EVENT_TYPES.ONE_C_RECOMMENDATION_SYNC
      };
      const eventType = eventTypeMap[entityType];
      if (!eventType) return sendJson(res, 400, { error: 'Unsupported one-c entity type' });
      return sendJson(res, 201, oneCSyncPlaceholder(eventType, body));
    }

    if (req.method === 'GET' && pathname === '/api/integrations/events') {
      return sendJson(res, 200, {
        items: db.listIntegrationEvents({
          status: requestUrl.searchParams.get('status') || undefined,
          sourceSystem: requestUrl.searchParams.get('sourceSystem') || undefined,
          limit: Number(requestUrl.searchParams.get('limit') || 20)
        })
      });
    }

    if (req.method === 'GET' && pathname.startsWith('/api/integrations/events/')) {
      const id = pathname.split('/')[4];
      const card = db.getIntegrationEventCard(id);
      return card ? sendJson(res, 200, card) : sendJson(res, 404, { error: 'Not found' });
    }

    if (req.method === 'POST' && pathname.startsWith('/api/integrations/events/') && pathname.endsWith('/retry')) {
      const id = pathname.split('/')[4];
      try {
        return sendJson(res, 200, integrationService.retryIntegrationEvent(id));
      } catch (error) {
        return sendJson(res, 404, { error: String(error.message || error) });
      }
    }



    if (req.method === 'GET' && pathname === '/api/reports/summary') {
      const params = {
        period: requestUrl.searchParams.get('period') || 'weekly',
        from: requestUrl.searchParams.get('from') || undefined,
        to: requestUrl.searchParams.get('to') || undefined,
        masterId: requestUrl.searchParams.get('masterId') || undefined,
        requestType: requestUrl.searchParams.get('requestType') || undefined,
        sourceChannel: requestUrl.searchParams.get('sourceChannel') || undefined,
        sourceSystem: requestUrl.searchParams.get('sourceSystem') || undefined
      };
      return sendJson(res, 200, reportingService.buildManagementSummary(params));
    }

    if (req.method === 'GET' && pathname === '/api/reports/requests') return sendJson(res, 200, reportingService.buildRequestsMetrics(Object.fromEntries(requestUrl.searchParams.entries())));
    if (req.method === 'GET' && pathname === '/api/reports/feedback') return sendJson(res, 200, reportingService.buildFeedbackMetrics(Object.fromEntries(requestUrl.searchParams.entries())));
    if (req.method === 'GET' && pathname === '/api/reports/quality') return sendJson(res, 200, reportingService.buildQualityMetrics(Object.fromEntries(requestUrl.searchParams.entries())));
    if (req.method === 'GET' && pathname === '/api/reports/masters') return sendJson(res, 200, reportingService.buildMasterMetrics(Object.fromEntries(requestUrl.searchParams.entries())));
    if (req.method === 'GET' && pathname === '/api/reports/sources') return sendJson(res, 200, reportingService.buildSourceMetrics(Object.fromEntries(requestUrl.searchParams.entries())));
    if (req.method === 'GET' && pathname === '/api/reports/recommendations') return sendJson(res, 200, reportingService.buildRecommendationMetrics(Object.fromEntries(requestUrl.searchParams.entries())));

    if (req.method === 'POST' && pathname === '/api/reports/snapshots') {
      const { body, invalidJson } = await readBody(req);
      if (invalidJson) return sendJson(res, 400, { error: 'Invalid JSON payload' });
      const snapshot = reportingService.buildPeriodicSnapshot(body || {});
      return sendJson(res, 201, snapshot);
    }

    if (req.method === 'GET' && pathname === '/api/reports/snapshots') {
      const limit = Number(requestUrl.searchParams.get('limit') || 50);
      return sendJson(res, 200, { items: reportingService.listSnapshots({ limit }) });
    }

    if (req.method === 'GET' && pathname.startsWith('/api/reports/snapshots/')) {
      const id = pathname.split('/')[4];
      const snapshot = reportingService.getSnapshotById(id);
      return snapshot ? sendJson(res, 200, snapshot) : sendJson(res, 404, { error: 'Not found' });
    }

    const matched = router.find((item) => item.path === pathname && item.method === req.method);
    if (matched) {
      const { body, invalidJson } = await readBody(req);
      if (invalidJson) return sendJson(res, 400, { error: 'Invalid JSON payload' });
      const payload = matched.handler ? await matched.handler({ body, config }) : { accepted: true };
      logger.info(`Accepted route: ${req.method} ${pathname}`);
      return sendJson(res, 200, payload);
    }

    return sendJson(res, 404, { error: 'Not found' });
  });
}

module.exports = { createServer };
