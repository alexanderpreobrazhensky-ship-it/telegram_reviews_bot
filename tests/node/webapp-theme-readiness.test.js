const test = require('node:test');
const assert = require('node:assert/strict');
const { createServer } = require('../../src/server');
const { loadConfig } = require('../../src/infrastructure/config');
const logger = require('../../src/infrastructure/logging/logger');
const db = require('../../src/infrastructure/db');

async function withServer(run) {
  db.resetStore();
  const config = loadConfig();
  const server = createServer({ config, logger });
  await new Promise((resolve) => server.listen(0, resolve));
  const port = server.address().port;

  try {
    await run(`http://127.0.0.1:${port}`);
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
}

test('webapp static assets are served and include theme-safe primitives', async () => {
  await withServer(async (base) => {
    const cssResponse = await fetch(`${base}/styles.css`);
    const jsResponse = await fetch(`${base}/webapp.js`);

    assert.equal(cssResponse.status, 200);
    assert.equal(jsResponse.status, 200);

    const css = await cssResponse.text();
    const js = await jsResponse.text();

    assert.match(css, /--tg-bg-color/);
    assert.match(css, /@media \(prefers-color-scheme: dark\)/);
    assert.match(js, /initTelegramTheme/);
    assert.match(js, /themeParams/);
  });
});
