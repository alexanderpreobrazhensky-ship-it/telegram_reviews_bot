const { MAX_API_BASE_URL } = require('../messaging');
const { withRetry } = require('../retry');

const DEFAULT_UPDATE_TYPES = Object.freeze(['message_created', 'message_callback', 'bot_started']);
const BOT_ROUTE_CONFIG = Object.freeze([
  { botKey: 'client', tokenKey: 'maxClientBotToken', routePath: '/max/client_bot/webhook' },
  { botKey: 'master', tokenKey: 'maxMasterBotToken', routePath: '/max/master_bot/webhook' }
]);

function normalizeUrl(value = '') {
  const raw = String(value || '').trim();
  if (!raw) return '';
  try {
    return new URL(raw).toString().replace(/\/$/, '');
  } catch {
    return '';
  }
}

function resolveWebhookBaseUrl(config = {}) {
  const explicitBase = normalizeUrl(config.maxWebhookBaseUrl || '');
  if (explicitBase) return explicitBase;

  const candidates = [config.maxWebAppUrl, config.webAppUrl].map((item) => String(item || '').trim()).filter(Boolean);
  for (const candidate of candidates) {
    try {
      const parsed = new URL(candidate);
      return `${parsed.origin}`;
    } catch {
      // ignore invalid candidate
    }
  }
  return '';
}

function buildWebhookUrl(baseUrl, routePath) {
  const normalizedBase = normalizeUrl(baseUrl);
  if (!normalizedBase) return '';
  try {
    const base = new URL(normalizedBase.endsWith('/') ? normalizedBase : `${normalizedBase}/`);
    return new URL(String(routePath || '').replace(/^\//, ''), base).toString().replace(/\/$/, '');
  } catch {
    return '';
  }
}

function normalizeUpdateTypes(value) {
  return Array.from(new Set((Array.isArray(value) ? value : [])
    .map((item) => String(item || '').trim())
    .filter(Boolean)))
    .sort();
}

function equalUpdateTypes(left, right) {
  const a = normalizeUpdateTypes(left);
  const b = normalizeUpdateTypes(right);
  return a.length === b.length && a.every((item, index) => item === b[index]);
}

async function maxApiRequest({ token, method = 'GET', path = '/subscriptions', body = undefined, operation = 'max.subscriptions' }) {
  const response = await withRetry(() => fetch(`${MAX_API_BASE_URL}${path}`, {
    method,
    headers: {
      Authorization: token,
      ...(body ? { 'Content-Type': 'application/json' } : {})
    },
    body: body ? JSON.stringify(body) : undefined
  }), { operation });

  const responseText = await response.text().catch(() => '');
  let payload = {};
  if (responseText) {
    try {
      payload = JSON.parse(responseText);
    } catch {
      payload = { raw: responseText };
    }
  }

  return { ok: response.ok, status: response.status, payload };
}

async function listSubscriptions(token) {
  return maxApiRequest({ token, method: 'GET', path: '/subscriptions', operation: 'max.subscriptions.list' });
}

async function createSubscription({ token, url, secret, updateTypes }) {
  return maxApiRequest({
    token,
    method: 'POST',
    path: '/subscriptions',
    body: { url, secret, update_types: updateTypes },
    operation: 'max.subscriptions.create'
  });
}

async function deleteSubscription({ token, url }) {
  return maxApiRequest({
    token,
    method: 'DELETE',
    path: `/subscriptions?url=${encodeURIComponent(url)}`,
    operation: 'max.subscriptions.delete'
  });
}

function normalizeSubscription(item = {}) {
  return {
    url: normalizeUrl(item.url || ''),
    secret: String(item.secret || '').trim(),
    updateTypes: normalizeUpdateTypes(item.update_types || item.updateTypes || [])
  };
}

async function reconcileBotSubscription({ config, logger, botKey, token, routePath, updateTypes = DEFAULT_UPDATE_TYPES }) {
  const expectedUrl = buildWebhookUrl(resolveWebhookBaseUrl(config), routePath);
  const expectedSecret = String(config.maxWebhookSecret || '').trim();
  const expectedTypes = normalizeUpdateTypes(updateTypes);

  if (!expectedUrl) {
    logger.warn('MAX subscription sync skipped: public webhook base URL is missing or invalid', { botKey, routePath, configuredBase: config.maxWebhookBaseUrl || config.maxWebAppUrl || config.webAppUrl || '' });
    return { botKey, ok: false, skipped: true, reason: 'MAX_WEBHOOK_BASE_URL_MISSING', expectedUrl: '' };
  }
  if (!token) {
    logger.warn('MAX subscription sync skipped: bot token is missing', { botKey, routePath });
    return { botKey, ok: false, skipped: true, reason: 'MAX_BOT_TOKEN_MISSING', expectedUrl };
  }
  if (!expectedSecret) {
    logger.warn('MAX subscription sync skipped: MAX_WEBHOOK_SECRET is missing', { botKey, routePath, expectedUrl });
    return { botKey, ok: false, skipped: true, reason: 'MAX_WEBHOOK_SECRET_MISSING', expectedUrl };
  }

  const listed = await listSubscriptions(token);
  if (!listed.ok) {
    logger.error('MAX subscription list failed', { botKey, routePath, expectedUrl, status: listed.status, payload: listed.payload });
    return { botKey, ok: false, reason: 'LIST_FAILED', expectedUrl, status: listed.status };
  }

  const subscriptions = Array.isArray(listed.payload?.subscriptions) ? listed.payload.subscriptions.map(normalizeSubscription) : [];
  const desiredSubscription = subscriptions.find((item) => item.url === expectedUrl);
  const matchesDesired = desiredSubscription && desiredSubscription.secret === expectedSecret && equalUpdateTypes(desiredSubscription.updateTypes, expectedTypes);

  if (matchesDesired && subscriptions.length === 1) {
    logger.info('MAX subscription already matches desired config', { botKey, routePath, expectedUrl, updateTypes: expectedTypes });
    return { botKey, ok: true, expectedUrl, updateTypes: expectedTypes, action: 'noop', subscriptions };
  }

  for (const subscription of subscriptions) {
    if (!subscription.url) continue;
    if (subscription.url === expectedUrl && matchesDesired && subscriptions.length > 1) continue;
    const deleted = await deleteSubscription({ token, url: subscription.url });
    if (!deleted.ok) {
      logger.error('MAX subscription delete failed', { botKey, routePath, expectedUrl, deleteUrl: subscription.url, status: deleted.status, payload: deleted.payload });
      return { botKey, ok: false, reason: 'DELETE_FAILED', expectedUrl, deleteUrl: subscription.url, status: deleted.status };
    }
    logger.warn('Removed stale MAX subscription', { botKey, routePath, deleteUrl: subscription.url, expectedUrl });
  }

  if (matchesDesired && subscriptions.length > 1) {
    logger.info('MAX subscription cleanup complete, desired webhook preserved', { botKey, routePath, expectedUrl, updateTypes: expectedTypes });
    return { botKey, ok: true, expectedUrl, updateTypes: expectedTypes, action: 'cleanup_only' };
  }

  const created = await createSubscription({ token, url: expectedUrl, secret: expectedSecret, updateTypes: expectedTypes });
  if (!created.ok) {
    logger.error('MAX subscription create failed', { botKey, routePath, expectedUrl, status: created.status, payload: created.payload, updateTypes: expectedTypes });
    return { botKey, ok: false, reason: 'CREATE_FAILED', expectedUrl, status: created.status };
  }

  logger.info('MAX subscription synchronized', { botKey, routePath, expectedUrl, updateTypes: expectedTypes });
  return { botKey, ok: true, expectedUrl, updateTypes: expectedTypes, action: 'recreated' };
}

async function reconcileMaxWebhookSubscriptions({ config, logger }) {
  if (!config?.maxEnabled) {
    logger.info('MAX subscription sync skipped because MAX is disabled');
    return { ok: true, skipped: true, reason: 'MAX_DISABLED', items: [] };
  }

  const items = [];
  for (const botConfig of BOT_ROUTE_CONFIG) {
    items.push(await reconcileBotSubscription({
      config,
      logger,
      botKey: botConfig.botKey,
      token: config[botConfig.tokenKey],
      routePath: botConfig.routePath
    }));
  }

  return { ok: items.every((item) => item.ok || item.skipped), items };
}

module.exports = {
  DEFAULT_UPDATE_TYPES,
  BOT_ROUTE_CONFIG,
  normalizeUrl,
  resolveWebhookBaseUrl,
  buildWebhookUrl,
  normalizeUpdateTypes,
  equalUpdateTypes,
  reconcileMaxWebhookSubscriptions
};
