function sanitizeHeaderValue(name, value) {
  const lower = String(name || '').toLowerCase();
  if (['authorization', 'x-max-bot-api-secret'].includes(lower)) {
    const raw = String(value || '');
    if (!raw) return '';
    if (raw.length <= 8) return `${raw.slice(0, 2)}***`;
    return `${raw.slice(0, 4)}***${raw.slice(-2)}`;
  }
  return value;
}

function collectWebhookHeaders(headers = {}, rawHeaders = []) {
  const sanitized = {};
  for (const [name, value] of Object.entries(headers || {})) {
    sanitized[name] = sanitizeHeaderValue(name, value);
  }
  const actualSecretHeaderName = Array.isArray(rawHeaders)
    ? rawHeaders.find((value, index) => index % 2 === 0 && String(value).toLowerCase() === 'x-max-bot-api-secret') || null
    : null;
  return {
    sanitized,
    hasSecretHeader: Boolean(findHeaderValue(headers, rawHeaders, 'x-max-bot-api-secret')),
    actualSecretHeaderName
  };
}

function findHeaderValue(headers = {}, rawHeaders = [], targetName = '') {
  const normalizedTarget = String(targetName || '').toLowerCase();
  for (const [name, value] of Object.entries(headers || {})) {
    if (String(name).toLowerCase() === normalizedTarget) return String(value || '');
  }
  if (Array.isArray(rawHeaders)) {
    for (let index = 0; index < rawHeaders.length; index += 2) {
      if (String(rawHeaders[index] || '').toLowerCase() === normalizedTarget) return String(rawHeaders[index + 1] || '');
    }
  }
  return '';
}

function isObjectPayload(body) {
  return Boolean(body) && typeof body === 'object' && !Array.isArray(body) && Object.keys(body).length > 0;
}

function validateMaxWebhookRequest({ config, headers = {}, rawHeaders = [], pathname = '', method = 'POST', logger, routeLabel = 'max_bot', token = '', body }) {
  const headerInfo = collectWebhookHeaders(headers, rawHeaders);
  const expectedSecret = String(config.maxWebhookSecret || '');
  const receivedSecret = findHeaderValue(headers, rawHeaders, 'x-max-bot-api-secret');
  const payloadValid = isObjectPayload(body);
  const secretPresent = Boolean(expectedSecret);
  const routeEnabled = Boolean(config.maxEnabled);
  const tokenPresent = Boolean(token);
  const secretCheckPassed = secretPresent && receivedSecret === expectedSecret;

  logger.info(`${routeLabel} webhook received`, {
    channel: 'max',
    pathname,
    method,
    headers: headerInfo.sanitized,
    hasSecretHeader: headerInfo.hasSecretHeader,
    actualSecretHeaderName: headerInfo.actualSecretHeaderName,
    maxEnabled: routeEnabled,
    maxTokenConfigured: tokenPresent,
    usesEnvMaxWebhookSecret: secretPresent,
    secretCheckPassed,
    payloadValid
  });

  if (!routeEnabled) {
    logger.warn(`${routeLabel} MAX route rejected because MAX is disabled`, { pathname, method });
    return { ok: false, error: 'MAX_DISABLED', statusCode: 503, headerInfo };
  }
  if (!tokenPresent) {
    logger.warn(`${routeLabel} MAX route rejected because bot token is missing`, { pathname, method });
    return { ok: false, error: 'MAX_BOT_TOKEN_MISSING', statusCode: 503, headerInfo };
  }
  if (!secretPresent) {
    logger.warn(`${routeLabel} MAX route rejected because MAX_WEBHOOK_SECRET is missing`, { pathname, method });
    return { ok: false, error: 'MAX_WEBHOOK_SECRET_MISSING', statusCode: 503, headerInfo };
  }
  if (!headerInfo.hasSecretHeader || !secretCheckPassed) {
    logger.warn(`${routeLabel} MAX secret check failed`, {
      pathname,
      method,
      hasSecretHeader: headerInfo.hasSecretHeader,
      actualSecretHeaderName: headerInfo.actualSecretHeaderName,
      receivedSecretPreview: sanitizeHeaderValue('x-max-bot-api-secret', receivedSecret),
      expectedSecretPreview: sanitizeHeaderValue('x-max-bot-api-secret', expectedSecret)
    });
    return { ok: false, error: 'INVALID_WEBHOOK_SECRET', statusCode: 403, headerInfo };
  }
  if (!payloadValid) {
    logger.warn(`${routeLabel} MAX route rejected because payload is invalid`, { pathname, method });
    return { ok: false, error: 'INVALID_MAX_PAYLOAD', statusCode: 400, headerInfo };
  }

  return { ok: true, headerInfo };
}

module.exports = {
  sanitizeHeaderValue,
  collectWebhookHeaders,
  findHeaderValue,
  validateMaxWebhookRequest
};
