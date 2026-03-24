function createDeepseekProvider({ config, fetchImpl = fetch }) {
  const name = 'deepseek';
  const endpoint = config.deepseekUrl || 'https://api.deepseek.com/chat/completions';

  function isConfigured() {
    return Boolean(config.deepseekApiKey);
  }

  async function invoke({ model, prompt, timeoutMs }) {
    if (!isConfigured()) {
      const error = new Error('DeepSeek API key missing');
      error.code = 'AI_DEEPSEEK_NOT_CONFIGURED';
      throw error;
    }
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), timeoutMs || config.timeoutMs || 8000);
    try {
      const response = await fetchImpl(endpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${config.deepseekApiKey}`
        },
        signal: controller.signal,
        body: JSON.stringify({ model, messages: [{ role: 'user', content: prompt }] })
      });
      if (!response.ok) {
        const error = new Error(`DeepSeek responded with ${response.status}`);
        error.code = response.status === 401 ? 'AI_AUTH_ERROR' : 'AI_PROVIDER_HTTP_ERROR';
        throw error;
      }
      const payload = await response.json().catch(() => ({}));
      const output = payload.choices?.[0]?.message?.content || 'OK';
      return { provider: name, model, output, raw: payload };
    } catch (error) {
      if (error?.name === 'AbortError') {
        const timeoutError = new Error('DeepSeek timeout');
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

module.exports = { createDeepseekProvider };
