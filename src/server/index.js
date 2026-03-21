const http = require('http');
const fs = require('fs');
const path = require('path');
const { URL } = require('url');
const db = require('../infrastructure/db');
const { REQUEST_TYPES } = require('../core/domain');
const { normalizePhone10, isValidPhone10, resolvePhoneInput } = require('../core/shared/phone');
const { validateClientRequestPayload: validateClientRequestPayloadDetailed } = require('../core/shared/requestValidation');
const { createRateLimiter } = require('../infrastructure/rate_limit');
const { filterRequestsForExport, mapRequestForExport, serializeCsv } = require('../infrastructure/export');
const { createRepositories } = require('../infrastructure/repositories');
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
      const contentType = String(req.headers['content-type'] || '');
      if (contentType.includes('application/x-www-form-urlencoded')) {
        return resolve({ body: Object.fromEntries(new URLSearchParams(raw).entries()), invalidJson: false });
      }
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

function sendHtml(res, status, html) {
  res.writeHead(status, { 'Content-Type': 'text/html; charset=utf-8' });
  res.end(html);
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

function sendText(res, status, body, contentType, headers = {}) {
  res.writeHead(status, { 'Content-Type': `${contentType}; charset=utf-8`, ...headers });
  res.end(body);
}

function requestIp(req) {
  return String(req.headers['x-forwarded-for'] || req.socket?.remoteAddress || 'unknown').split(',')[0].trim();
}

function applyRateLimit(res, limiter, key, logger, context) {
  const result = limiter.consume(key);
  if (result.ok) return null;
  logger.warn('rate limit exceeded', { ...context, key, retryAfterMs: result.retryAfterMs, limit: result.limit, windowMs: result.windowMs });
  sendJson(res, 429, { error: 'RATE_LIMITED', retryAfterMs: result.retryAfterMs });
  return result;
}

function exportFilename(format) {
  const suffix = new Date().toISOString().replace(/[.:]/g, '-');
  return `requests-export-${suffix}.${format === 'json' ? 'json' : 'csv'}`;
}


function validateClientRequestPayload(body = {}, type) {
  return validateClientRequestPayloadDetailed(body, type).errors;
}

function validateClientRequestPayloadWithPhone(body = {}, type) {
  return validateClientRequestPayloadDetailed(body, type);
}

function injectConfigIntoHtml(html, config) {
  const script = `<script>window.__WEBAPP_TELEGRAM_CHANNEL_LINK__=${JSON.stringify(config.webappTelegramChannelLink || '')};window.__WEBAPP_RUNTIME__=${JSON.stringify({
    webAppUrl: config.webAppUrl || '',
    maxWebAppUrl: config.maxWebAppUrl || config.webAppUrl || '',
    maxBotName: config.maxBotName || '',
    maxDeepLinkBaseUrl: config.maxDeepLinkBaseUrl || ''
  })};</script>`;
  return html.includes('</body>') ? html.replace('</body>', `${script}</body>`) : `${html}${script}`;
}


async function sendTelegramMessage(token, chatId, text, extra = {}) {
  if (!token || !chatId) return false;
  await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ chat_id: chatId, text, ...extra })
  }).catch(() => {});
  return true;
}

async function duplicateToMastersChat({ config, request, payload }) {
  if (!config.telegramMasterBotToken || !config.telegramMastersChatId) return;
  const text = [
    `Новая заявка: ${request.id}`,
    `Тип: ${request.requestType}`,
    `Телефон: ${payload.phone || '-'}`,
    `VIN: ${payload.vin || '-'}`,
    `Описание: ${payload.description || payload.question || payload.changeDetails || '-'}`
  ].join('\n');
  await sendTelegramMessage(config.telegramMasterBotToken, Number(config.telegramMastersChatId), text, {
    reply_markup: {
      inline_keyboard: [
        [
          { text: 'Назначить', callback_data: `req:${request.id}:assigned` },
          { text: 'Ждём клиента', callback_data: `req:${request.id}:awaiting_client` }
        ],
        [
          { text: 'Запланировать', callback_data: `req:${request.id}:scheduled` },
          { text: 'В сервисе', callback_data: `req:${request.id}:in_service` }
        ],
        [
          { text: 'Завершить', callback_data: `req:${request.id}:done` },
          { text: 'Отменить', callback_data: `req:${request.id}:cancelled` }
        ],
        [{ text: 'Подробнее', callback_data: `card:${request.id}` }]
      ]
    }
  });
}

function createClientRequest({ body, type, sourceChannel = 'webapp', repositories = createRepositories({ db }) }) {
  const normalizedPhone = resolvePhoneInput(body);
  const client = repositories.requests.createClient({
    fullName: body.fullName,
    phone: normalizedPhone,
    telegramId: body.telegramId ? String(body.telegramId) : null,
    maxId: body.maxId ? String(body.maxId) : null,
    preferredChannel: sourceChannel.startsWith('max_') ? 'max' : (body.telegramId ? 'telegram' : null)
  });
  const vehicle = repositories.requests.createVehicle({
    clientId: client.id,
    brand: body.brand,
    model: body.model || body.car,
    year: body.year,
    vin: body.vin,
    plateNumber: body.plateNumber
  });
  const request = repositories.requests.create({
    clientId: client.id,
    vehicleId: vehicle?.id || null,
    requestType: type,
    description: body.description || body.question || body.changeDetails || '',
    sourceChannel,
    payload: {
      wasClientBefore: body.wasClientBefore || '',
      visitDate: body.visitDate || '',
      car: body.car || '',
      question: body.question || '',
      changeDetails: body.changeDetails || '',
      contactSource: body.contactSource || body.nativeContact?.source || 'manual',
      nativeContact: body.nativeContact || null
    }
  });
  db.createCommunicationEvent({
    clientId: client.id,
    requestId: request.id,
    source: sourceChannel === 'webapp' || sourceChannel === 'max_webapp' ? 'webapp' : 'bot',
    channel: sourceChannel,
    direction: 'inbound',
    payload: { action: 'request_created', type, contactSource: body.contactSource || body.nativeContact?.source || 'manual' }
  });
  return { client, vehicle, request };
}

function trackAnalytics(event) {
  return db.createAnalyticsEvent(event);
}

function internalAdminSet(config) {
  return new Set([
    ...(config.internalAdminWhitelist || []),
    ...(config.masterBotAdminIds || []),
    ...(config.maxMasterBotAdminIds || [])
  ].map((item) => String(item || '').trim()).filter(Boolean));
}

function resolveInternalAdminId(req, requestUrl) {
  return String(
    req.headers['x-admin-id']
      || req.headers['x-internal-admin-id']
      || requestUrl.searchParams.get('admin_id')
      || requestUrl.searchParams.get('adminId')
      || ''
  ).trim();
}

function isInternalAuthorized(req, requestUrl, config) {
  const adminId = resolveInternalAdminId(req, requestUrl);
  const whitelist = internalAdminSet(config);
  return { ok: whitelist.size > 0 && whitelist.has(adminId), adminId, whitelistSize: whitelist.size };
}

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function renderInternalRequestsPage({ requests, filters, adminId, requestCards }) {
  const selected = (value, expected) => String(value || '') === String(expected || '') ? ' selected' : '';
  const rows = requests.map((request) => {
    const card = requestCards.get(request.id);
    const eventsHtml = (card?.requestEvents || [])
      .map((event) => `<li><strong>${escapeHtml(event.canonicalEventType || event.eventType)}</strong> · ${escapeHtml(event.createdAt)} · ${escapeHtml(event.actorType || event.actorRole || '-')} · ${escapeHtml(event.actorId || '-')} · ${escapeHtml(event.oldValue || event.oldStatus || '-')} → ${escapeHtml(event.newValue || event.newStatus || '-')}</li>`)
      .join('');
    return `
      <tr>
        <td>${escapeHtml(request.id)}</td>
        <td>${escapeHtml(request.createdAt)}</td>
        <td>
          <form method="POST" action="/internal/requests/${encodeURIComponent(request.id)}/status?admin_id=${encodeURIComponent(adminId)}">
            <select name="status">
              ${['new', 'assigned', 'awaiting_client', 'scheduled', 'in_service', 'done', 'cancelled'].map((status) => `<option value="${status}"${selected(request.status, status)}>${status}</option>`).join('')}
            </select>
            <input type="text" name="comment" placeholder="comment / reason"/>
            <button type="submit">Save</button>
          </form>
        </td>
        <td>${escapeHtml(card?.client?.phone || '-')}</td>
        <td>${escapeHtml(request.sourceChannel || '-')}</td>
        <td>${escapeHtml(request.requestType || '-')}</td>
        <td>${escapeHtml(request.assignedTo || '-')}</td>
      </tr>
      <tr>
        <td colspan="7">
          <details>
            <summary>Events (${(card?.requestEvents || []).length})</summary>
            <ul>${eventsHtml || '<li>No events</li>'}</ul>
          </details>
        </td>
      </tr>
    `;
  }).join('');

  return `<!doctype html>
  <html lang="en">
    <head>
      <meta charset="utf-8"/>
      <title>Internal Requests</title>
      <style>
        body { font-family: Arial, sans-serif; margin: 24px; }
        table { width: 100%; border-collapse: collapse; }
        th, td { border: 1px solid #ddd; padding: 8px; vertical-align: top; }
        form.inline, .filters { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
        input, select, button { padding: 6px; }
        details { margin-top: 8px; }
      </style>
    </head>
    <body>
      <h1>Internal Requests</h1>
      <p>Admin: ${escapeHtml(adminId)}</p>
      <form class="filters" method="GET" action="/internal/requests">
        <input type="hidden" name="admin_id" value="${escapeHtml(adminId)}"/>
        <label>Status <select name="status"><option value="">all</option>${['new', 'assigned', 'awaiting_client', 'scheduled', 'in_service', 'done', 'cancelled'].map((status) => `<option value="${status}"${selected(filters.status, status)}>${status}</option>`).join('')}</select></label>
        <label>Channel <select name="channel"><option value="">all</option>${['webapp', 'max_webapp', 'telegram_chat', 'max_chat'].map((channel) => `<option value="${channel}"${selected(filters.channel, channel)}>${channel}</option>`).join('')}</select></label>
        <label>Type <select name="request_type"><option value="">all</option>${Object.values(REQUEST_TYPES).map((type) => `<option value="${type}"${selected(filters.requestType, type)}>${type}</option>`).join('')}</select></label>
        <button type="submit">Apply</button>
      </form>
      <table>
        <thead>
          <tr><th>ID</th><th>Created</th><th>Status</th><th>Phone</th><th>Channel</th><th>Type</th><th>Assigned</th></tr>
        </thead>
        <tbody>${rows || '<tr><td colspan="7">No requests</td></tr>'}</tbody>
      </table>
    </body>
  </html>`;
}

function buildHealthPayload(config) {
  return {
    status: 'ok',
    uptimeSeconds: Math.round(process.uptime()),
    env: config.nodeEnv,
    timestamp: new Date().toISOString(),
    envAudit: config.envAudit
  };
}

function buildDbHealthPayload() {
  const runtime = db.getDbRuntimeInfo();
  const tables = db.listTables();
  return {
    status: 'ok',
    db: {
      type: runtime.type,
      path: runtime.path,
      initStatus: runtime.lastInitStatus,
      tables
    }
  };
}

function buildMaxHealthPayload(config) {
  const payload = {
    status: config.maxEnabled ? 'enabled' : 'disabled',
    maxEnabled: Boolean(config.maxEnabled),
    tokensConfigured: Boolean(config.maxClientBotToken || config.maxMasterBotToken),
    webhookSecretConfigured: Boolean(config.maxWebhookSecret),
    botNameConfigured: Boolean(config.maxBotName)
  };
  if (config.maxDiagnosticsEnabled) {
    payload.diagnostics = {
      hasClientBotToken: Boolean(config.maxClientBotToken),
      hasMasterBotToken: Boolean(config.maxMasterBotToken),
      hasWebAppUrl: Boolean(config.maxWebAppUrl),
      hasDeepLinkBaseUrl: Boolean(config.maxDeepLinkBaseUrl)
    };
  }
  return payload;
}


function createServer({ config, logger }) {
  const router = [];
  const repositories = createRepositories({ db });
  const reportingService = createReportingService({ db });
  const webappLimiter = createRateLimiter({ windowMs: config.webappRateLimitWindowMs, limit: config.webappRateLimitMax });
  const webhookLimiter = createRateLimiter({ windowMs: config.webhookRateLimitWindowMs, limit: config.webhookRateLimitMax });
  require('../interfaces/client_bot').registerClientBotRoutes(router);
  require('../interfaces/master_bot').registerMasterBotRoutes(router);
  require('../interfaces/integration_bot').registerIntegrationBotRoutes(router);

  return http.createServer(async (req, res) => {
    const requestUrl = new URL(req.url, 'http://localhost');
    const pathname = requestUrl.pathname;
    logger.info('http request received', { method: req.method, pathname, ip: requestIp(req) });

    if (req.method === 'GET' && pathname === '/health') return sendJson(res, 200, buildHealthPayload(config));
    if (req.method === 'GET' && pathname === '/health/db') return sendJson(res, 200, buildDbHealthPayload());
    if (req.method === 'GET' && pathname === '/health/max') return sendJson(res, 200, buildMaxHealthPayload(config));

    if (req.method === 'GET' && pathname === '/internal/requests') {
      const auth = isInternalAuthorized(req, requestUrl, config);
      if (!auth.ok) return sendJson(res, 403, { error: 'FORBIDDEN', details: ['Provide a whitelisted admin_id query parameter or x-admin-id header.'] });
      const filters = {
        status: requestUrl.searchParams.get('status') || '',
        channel: requestUrl.searchParams.get('channel') || '',
        requestType: requestUrl.searchParams.get('request_type') || ''
      };
      const requests = db.listRequests({
        statuses: filters.status ? [filters.status] : undefined,
        channel: filters.channel || undefined,
        requestType: filters.requestType || undefined
      }).slice(-100).reverse();
      const requestCards = new Map(requests.map((item) => [item.id, db.getRequestCard(item.id)]));
      return sendHtml(res, 200, renderInternalRequestsPage({ requests, filters, adminId: auth.adminId, requestCards }));
    }

    if (req.method === 'GET' && pathname === '/internal/export') {
      const auth = isInternalAuthorized(req, requestUrl, config);
      if (!auth.ok) return sendJson(res, 403, { error: 'FORBIDDEN' });
      const format = requestUrl.searchParams.get('format') === 'json' ? 'json' : 'csv';
      const statuses = (requestUrl.searchParams.get('status') || '').split(',').map((item) => item.trim()).filter(Boolean);
      const filters = { from: requestUrl.searchParams.get('from') || '', to: requestUrl.searchParams.get('to') || '', statuses };
      const items = filterRequestsForExport(repositories.requests.list({ statuses: statuses.length ? statuses : undefined }), filters)
        .map((request) => mapRequestForExport(request, repositories.requests.getCard(request.id) || {}));
      logger.info('internal export generated', { adminId: auth.adminId, format, count: items.length, filters });
      if (format === 'json') {
        return sendText(res, 200, JSON.stringify({ items }, null, 2), 'application/json', { 'Content-Disposition': `attachment; filename="${exportFilename(format)}"` });
      }
      return sendText(res, 200, serializeCsv(items), 'text/csv', { 'Content-Disposition': `attachment; filename="${exportFilename(format)}"` });
    }

    if (req.method === 'POST' && /^\/internal\/requests\/[^/]+\/status$/.test(pathname)) {
      const auth = isInternalAuthorized(req, requestUrl, config);
      if (!auth.ok) return sendJson(res, 403, { error: 'FORBIDDEN' });
      const requestId = pathname.split('/')[3];
      const { body, invalidJson } = await readBody(req);
      if (invalidJson) return sendJson(res, 400, { error: 'Invalid JSON payload' });
      const formBody = Object.keys(body || {}).length ? body : {};
      const result = db.updateRequestStatus({
        requestId,
        toStatus: formBody.status,
        comment: formBody.comment || null,
        lostReason: formBody.comment || null,
        actorId: auth.adminId,
        actorRole: 'admin'
      });
      if ((req.headers['content-type'] || '').includes('application/json')) {
        return sendJson(res, result?.error ? 400 : 200, result);
      }
      res.writeHead(303, { Location: `/internal/requests?admin_id=${encodeURIComponent(auth.adminId)}` });
      return res.end();
    }

    if (req.method === 'GET' && (pathname === '/styles.css' || pathname === '/webapp.js')) {
      const staticPath = path.join(process.cwd(), 'public', pathname.slice(1));
      return serveFile(res, staticPath, pathname.endsWith('.css') ? 'text/css' : 'application/javascript');
    }

    if (req.method === 'GET' && pathname === '/logo.png') {
      try {
        const content = fs.readFileSync(path.join(process.cwd(), 'logo.png'));
        res.writeHead(200, { 'Content-Type': 'image/png' });
        return res.end(content);
      } catch {
        return sendJson(res, 404, { error: 'Not found' });
      }
    }

    const webPages = ['/', '/requests', '/recommendations', '/forms/service-request', '/forms/parts-request', '/forms/consultation', '/forms/warranty-request', '/forms/data-change-request'];
    if (req.method === 'GET' && webPages.includes(pathname)) {
      try {
        const html = fs.readFileSync(path.join(process.cwd(), 'public', 'index.html'), 'utf8');
        res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
        return res.end(injectConfigIntoHtml(html, config));
      } catch {
        return sendJson(res, 404, { error: 'Not found' });
      }
    }

    if (req.method === 'POST' && pathname.startsWith('/api/client/requests/')) {
      const limited = applyRateLimit(res, webappLimiter, `webapp:${requestIp(req)}`, logger, { pathname, channel: 'webapp' });
      if (limited) return;
      const { body, invalidJson } = await readBody(req);
      if (invalidJson) return sendJson(res, 400, { error: 'Invalid JSON payload' });

      const typeMap = {
        '/api/client/requests/service': REQUEST_TYPES.SERVICE,
        '/api/client/requests/parts': REQUEST_TYPES.PARTS,
        '/api/client/requests/consultation': REQUEST_TYPES.CONSULTATION,
        '/api/client/requests/warranty': REQUEST_TYPES.WARRANTY,
        '/api/client/requests/data-change': REQUEST_TYPES.DATA_CHANGE
      };
      const type = typeMap[pathname];
      if (!type) return sendJson(res, 404, { error: 'Not found' });

      const { errors, normalizedPhone } = validateClientRequestPayloadWithPhone(body, type);
      body.phone = normalizedPhone;
      if (errors.length) {
        trackAnalytics({
          eventType: 'request_failed',
          channel: body.sourceChannel === 'max_webapp' ? 'max' : 'telegram',
          platform: body.sourceChannel === 'max_webapp' ? 'max' : 'telegram',
          requestType: type,
          status: 'validation_error',
          metaJson: { errors }
        });
        logger.warn('client request validation failed', { pathname, errors, ip: requestIp(req) });
        return sendJson(res, 400, { error: 'Validation error', details: errors });
      }

      const sourceChannel = body.sourceChannel === 'max_webapp' ? 'max_webapp' : 'webapp';
      const duplicate = repositories.requests.findRecentDuplicate({
        requestType: type,
        phone: body.phone,
        vin: body.vin,
        text: body.description || body.question || body.changeDetails || '',
        withinMs: config.webappDedupeWindowMs
      });
      const { client, request: created } = createClientRequest({ body, type, sourceChannel, repositories });
      if (duplicate && duplicate.id !== created.id) {
        repositories.requests.markDuplicate({
          requestId: created.id,
          duplicateOfRequestId: duplicate.id,
          metaJson: { sourceChannel, phone: body.phone }
        });
        trackAnalytics({
          eventType: 'request_duplicate_detected',
          channel: sourceChannel === 'max_webapp' ? 'max' : 'telegram',
          platform: sourceChannel === 'max_webapp' ? 'max' : 'telegram',
          requestType: type,
          requestId: created.id,
          clientId: client.id,
          status: 'duplicate_detected',
          metaJson: { duplicateRequestId: duplicate.id }
        });
      }
      trackAnalytics({
        eventType: 'request_created',
        channel: sourceChannel === 'max_webapp' ? 'max' : 'telegram',
        platform: sourceChannel === 'max_webapp' ? 'max' : 'telegram',
        requestType: type,
        requestId: created.id,
        clientId: client.id,
        status: created.status,
        metaJson: { sourceChannel }
      });
      await duplicateToMastersChat({ config, request: created, payload: body });
      if (created.requestType === REQUEST_TYPES.COMPLAINT) {
        await duplicateToMastersChat({ config, request: created, payload: body });
      }
      return sendJson(res, 201, duplicate ? { ...created, deduplicated: true, duplicateOfRequestId: duplicate.id } : created);
    }

    if (req.method === 'POST' && pathname === '/api/analytics/events') {
      const { body, invalidJson } = await readBody(req);
      if (invalidJson) return sendJson(res, 400, { error: 'Invalid JSON payload' });
      const event = trackAnalytics({
        eventType: body.eventType,
        channel: body.channel || null,
        platform: body.platform || null,
        requestType: body.requestType || null,
        requestId: body.requestId || null,
        clientId: body.clientId || null,
        status: body.status || null,
        metaJson: body.metaJson || {}
      });
      return sendJson(res, 201, event);
    }

    if (req.method === 'POST' && /^\/api\/requests\/[^/]+\/assign$/.test(pathname)) {
      const { body, invalidJson } = await readBody(req);
      if (invalidJson) return sendJson(res, 400, { error: 'Invalid JSON payload' });
      const requestId = pathname.split('/')[3];
      const result = db.updateRequestAssignment({
        requestId,
        assignedTo: body.assignedTo,
        assignedBy: body.assignedBy || body.actorId || 'admin',
        actorId: body.actorId || body.assignedBy || null,
        actorRole: body.actorRole || 'admin',
        actorType: body.actorType || body.actorRole || 'admin',
        metaJson: body.metaJson || {}
      });
      return sendJson(res, result?.error ? 400 : 200, result);
    }

    if (req.method === 'POST' && /^\/api\/requests\/[^/]+\/status$/.test(pathname)) {
      const { body, invalidJson } = await readBody(req);
      if (invalidJson) return sendJson(res, 400, { error: 'Invalid JSON payload' });
      const requestId = pathname.split('/')[3];
      const result = db.updateRequestStatus({
        requestId,
        toStatus: body.status,
        comment: body.comment || null,
        lostReason: body.comment || null,
        actorId: body.actorId || null,
        actorRole: body.actorRole || 'admin'
      });
      return sendJson(res, result?.error ? 400 : 200, result);
    }

    if (req.method === 'GET' && pathname === '/api/client/requests') {
      const phone = requestUrl.searchParams.get('phone');
      const normalizedPhone = phone ? normalizePhone10(phone) : null;
      if (phone && !isValidPhone10(normalizedPhone)) return sendJson(res, 400, { error: 'Validation error', details: ['phone must normalize to exactly 10 digits without +7/8'] });
      return sendJson(res, 200, { items: db.listRequests({ phone: normalizedPhone, telegramId: requestUrl.searchParams.get('telegramId'), maxId: requestUrl.searchParams.get('maxId') }) });
    }

    if (req.method === 'GET' && pathname === '/api/client/recommendations') {
      const telegramId = requestUrl.searchParams.get('telegramId');
      if (!telegramId) return sendJson(res, 401, { error: 'AUTH_REQUIRED', details: ['telegramId is required'] });
      const client = db.findClientByTelegramId(telegramId);
      if (!client) return sendJson(res, 200, { items: [] });
      return sendJson(res, 200, { items: db.listRecommendations({ telegramId, requireSynced: true }) });
    }

    if (req.method === 'POST' && pathname.startsWith('/api/client/recommendations/') && pathname.endsWith('/interest')) {
      const id = pathname.split('/')[4];
      const { body } = await readBody(req);
      const telegramId = String(body.telegramId || '');
      if (!telegramId) return sendJson(res, 401, { error: 'AUTH_REQUIRED' });
      const client = db.findClientByTelegramId(telegramId);
      if (!client) return sendJson(res, 404, { error: 'CLIENT_NOT_FOUND' });
      const updated = db.markRecommendationInterest(id);
      if (!updated) return sendJson(res, 404, { error: 'Not found' });
      const request = db.createRequest({
        clientId: client.id,
        vehicleId: null,
        requestType: REQUEST_TYPES.SERVICE,
        description: `Клиент хочет устранить рекомендацию: ${updated.text}`,
        sourceChannel: body.sourceChannel === 'max_webapp' ? 'max_webapp' : 'webapp',
        payload: { recommendationId: updated.id, recommendationInterest: true }
      });
      await duplicateToMastersChat({ config, request, payload: { phone: client.phone, vin: '', description: request.description } });
      return sendJson(res, 201, { recommendation: updated, request });
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
      if (pathname.includes('/webhook')) {
        const limited = applyRateLimit(res, webhookLimiter, `webhook:${pathname}:${requestIp(req)}`, logger, { pathname, channel: 'webhook' });
        if (limited) return;
      }
      const { body, invalidJson } = await readBody(req);
      if (invalidJson) return sendJson(res, 400, { error: 'Invalid JSON payload' });
      const payload = matched.handler
        ? await matched.handler({ body, config, headers: req.headers, pathname, method: req.method, rawHeaders: req.rawHeaders || [] })
        : { accepted: true };
      logger.info(`Accepted route: ${req.method} ${pathname}`);
      return sendJson(res, payload?.statusCode || 200, payload);
    }

    return sendJson(res, 404, { error: 'Not found' });
  });
}

module.exports = { createServer, normalizePhone10, isValidPhone10, validateClientRequestPayload, createClientRequest };
