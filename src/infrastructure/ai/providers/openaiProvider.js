function createOpenAiProvider({ config, fetchImpl = fetch }) {
  const name = 'openai';
  const endpoint = config.openaiUrl || 'https://api.openai.com/v1/chat/completions';

  function isConfigured() {
    return Boolean(config.openaiApiKey);
  }

  async function invoke({ model, prompt, timeoutMs }) {
    if (!isConfigured()) {
      const error = new Error('OpenAI API key missing');
      error.code = 'AI_OPENAI_NOT_CONFIGURED';
      throw error;
    }
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), timeoutMs || config.timeoutMs || 8000);
    try {
      const response = await fetchImpl(endpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${config.openaiApiKey}`
        },
        signal: controller.signal,
        body: JSON.stringify({ model, messages: [{ role: 'user', content: prompt }] })
      });
      if (!response.ok) {
        const error = new Error(`OpenAI responded with ${response.status}`);
        error.code = response.status === 401 ? 'AI_AUTH_ERROR' : 'AI_PROVIDER_HTTP_ERROR';
        throw error;
      }
      const payload = await response.json().catch(() => ({}));
      const output = payload.choices?.[0]?.message?.content || 'OK';
      return { provider: name, model, output, raw: payload };
    } catch (error) {
      if (error?.name === 'AbortError') {
        const timeoutError = new Error('OpenAI timeout');
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

module.exports = { createOpenAiProvider };
