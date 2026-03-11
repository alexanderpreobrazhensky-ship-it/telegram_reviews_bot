# Единая платформа автосервиса (Node.js / BotHost)

## Production contract (final)
- Runtime: **Node.js**
- Entrypoint: **`app.js`**
- Manifest: **`package.json`**
- Deploy branch: **`main`**
- Platform target: **BotHost**
- Production path: **Node-first**

## Deploy fixes applied
- Lockfile contract приведён к `npm ci`: добавлен актуальный `package-lock.json`, конфликтующих lock-артефактов нет.
- Runtime port берётся из `process.env.PORT`; fallback `3000` используется только для локального запуска.
- Legacy Python deployment traces нейтрализованы (Dockerfile, BotHost entrypoint, CI).

## Quick start (local)
```bash
npm ci
npm start
```

## ENV audit (runtime)
### Обязательные для production
- `PORT` — runtime-порт платформы (BotHost передаёт автоматически).
- `TELEGRAM_CLIENT_BOT_TOKEN`
- `TELEGRAM_MASTER_BOT_TOKEN`
- `TELEGRAM_INTEGRATION_BOT_TOKEN`

### Рекомендуемые
- `WEBAPP_URL` — Mini App URL (использовать `https://вашлогин.bothost.ru`).
- `DB_FILE_PATH` — путь к persistent file DB.
- `NODE_ENV=production`

### Optional
- `ENABLE_INTEGRATION_WORKER`
- `ONE_C_SYNC_ENABLED`
- `EMAIL_IMPORT_ENABLED`
- `ONE_C_WEBHOOK_SECRET`
- `INTEGRATION_RETRY_MAX`
- `INTEGRATION_RETRY_DELAY_SECONDS`
- `FEEDBACK_REQUEST_DELAY_MINUTES`
- `SCHEDULER_INTERVAL_MS`
- `SCHEDULER_BATCH_SIZE`
- `SCHEDULER_MAX_ATTEMPTS`
- `SCHEDULER_STUCK_TIMEOUT_MS`

## BotHost deploy narrative
1. Branch: `main`.
2. Runtime: Node.js 18+.
3. Main file: `app.js`.
4. Указать ENV (`PORT`, 3 Telegram token, `WEBAPP_URL`, `DB_FILE_PATH`).
5. Деплоить через update-from-git.

### Domain strategy
- Production base domain: `https://вашлогин.bothost.ru`.
- Этот домен использовать для:
  - `WEBAPP_URL`
  - Telegram webhooks
  - BotFather menu button
- Случайный дефолтный BotHost-домен не использовать как production-base.

## Webhook routes
- `POST /telegram/client_bot/webhook`
- `POST /telegram/master_bot/webhook`
- `POST /telegram/integration_bot/webhook`

## API / routes (smoke critical)
- `GET /health`
- `GET /`, `/requests`, `/recommendations`
- `GET /forms/service-request`, `/forms/parts-request`, `/forms/consultation`, `/forms/warranty-request`, `/forms/data-change-request`
- `GET /styles.css`, `/webapp.js`
- `POST /api/client/requests/service|parts|consultation|warranty|data-change`
- `GET /api/client/requests`
- `GET /api/client/recommendations`
- `POST /api/client/recommendations/:id/interest`
- `POST /api/integrations/email`
- `POST /api/integrations/manual`
- `POST /api/integrations/one-c/:entityType`
- `GET /api/integrations/events`
- `GET /api/integrations/events/:id`
- `POST /api/integrations/events/:id/retry`
- `GET /api/reports/summary`
- `GET /api/reports/{requests|feedback|quality|masters|sources|recommendations}`
- `POST /api/reports/snapshots`
- `GET /api/reports/snapshots`
- `GET /api/reports/snapshots/:id`

## Post-deploy smoke plan
1. Проверить `GET /health`.
2. Проверить `GET /`, `GET /styles.css`, `GET /webapp.js`.
3. Проверить WebApp с `https://вашлогин.bothost.ru` и из Telegram Mini App.
4. Проверить `/start` во всех 3 ботах.
5. Проверить отчётность: `GET /api/reports/summary?period=weekly`.
6. Проверить snapshot: `POST /api/reports/snapshots`.
7. Проверить HTTPS: нет `NET::ERR_CERT_AUTHORITY_INVALID` и browser warnings.
8. Проверить light/dark theme вручную.

## Tests
```bash
npm test
```
