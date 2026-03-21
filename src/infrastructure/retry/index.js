const logger = require('../logging/logger');

function isRetryableError(error) {
  const message = String(error?.message || error || '').toUpperCase();
  return [
    'TIMEOUT',
    'ETIMEDOUT',
    'ECONNRESET',
    'EAI_AGAIN',
    'ENOTFOUND',
    'TEMP',
    'SQLITE_BUSY',
    'SQLITE_LOCKED',
    '429',
    '503',
    '502',
    '504'
  ].some((token) => message.includes(token));
}

async function withRetry(action, options = {}) {
  const {
    attempts = 3,
    delayMs = 250,
    factor = 2,
    operation = 'operation',
    logger: customLogger = logger,
    shouldRetry = isRetryableError
  } = options;

  let attempt = 0;
  let lastError;
  while (attempt < attempts) {
    attempt += 1;
    try {
      return await action({ attempt });
    } catch (error) {
      lastError = error;
      const retryable = attempt < attempts && shouldRetry(error);
      customLogger.warn('retryable operation failed', {
        operation,
        attempt,
        attempts,
        retryable,
        error: String(error?.message || error)
      });
      if (!retryable) break;
      const waitMs = delayMs * Math.max(1, factor ** (attempt - 1));
      await new Promise((resolve) => setTimeout(resolve, waitMs));
    }
  }
  throw lastError;
}

module.exports = { withRetry, isRetryableError };
