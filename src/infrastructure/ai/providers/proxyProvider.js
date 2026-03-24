function createProxyProvider({ config, fetchImpl = fetch }) {
  const name = 'proxy';

  function isConfigured() {
    return Boolean(config.proxyUrl && config.proxyToken);
  }

  async function invoke({ model, prompt, timeoutMs }) {
    if (!isConfigured()) {
      const error = new Error('Proxy provider is not configured');
      error.code = 'AI_PROXY_NOT_CONFIGURED';
      throw error;
    }
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), timeoutMs || config.timeoutMs || 8000);
    try {
      const response = await fetchImpl(config.proxyUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${config.proxyToken}`
        },
        signal: controller.signal,
        body: JSON.stringify({ model, prompt, healthcheck: true })
      });
      if (!response.ok) {
        const error = new Error(`Proxy responded with ${response.status}`);
        error.code = response.status === 401 ? 'AI_AUTH_ERROR' : 'AI_PROVIDER_HTTP_ERROR';
        throw error;
      }
      const payload = await response.json().catch(() => ({}));
      return {
        provider: name,
        model: payload.model || model,
        output: payload.output || payload.text || 'OK',
        raw: payload
      };
    } catch (error) {
      if (error?.name === 'AbortError') {
        const timeoutError = new Error('Proxy timeout');
        timeoutError.code = 'AI_TIMEOUT';
        throw timeoutError;
      }
      throw error;
    } finally {
      clearTimeout(timeout);
    }
  }

  return { name, isConfigured, invoke };
}

module.exports = { createProxyProvider };
