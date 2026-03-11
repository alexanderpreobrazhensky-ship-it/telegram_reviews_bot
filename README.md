# Единая платформа автосервиса (Node.js / BotHost)

## Production contract (неизменяемый)
- Runtime: **Node.js**
- Entrypoint: **`app.js`**
- Manifest: **`package.json`**
- Deploy branch: **`main`**
- Python не участвует в production startup path.

## Что реализовано
- `client_bot` + WebApp MVP.
- `master_bot` MVP.
- feedback/quality flow MVP.
- integration layer MVP (email/manual + one_c skeleton).
- analytics/reporting MVP + snapshots.
- scheduler/worker для задач (feedback/reminders).

## Быстрый запуск локально
```bash
npm install
npm start
```

## ENV
### Обязательные
- `PORT`
- `TELEGRAM_CLIENT_BOT_TOKEN`
- `TELEGRAM_MASTER_BOT_TOKEN`
- `TELEGRAM_INTEGRATION_BOT_TOKEN`

### Рекомендуемые
- `WEBAPP_URL` — ссылка для кнопки WebApp в client bot
- `DB_FILE_PATH` — путь к файловой БД (для BotHost указывать persistent volume)
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

## BotHost deploy guide
1. В BotHost выбрать ветку `main`.
2. Runtime: Node.js 18+.
3. Main file: `app.js`.
4. Прописать обязательные ENV (минимум 3 Telegram token + `PORT`).
5. Указать `DB_FILE_PATH` на постоянное хранилище.
6. Запустить деплой.

## Webhook routes (для Telegram setWebhook)
- `POST /telegram/client_bot/webhook`
- `POST /telegram/master_bot/webhook`
- `POST /telegram/integration_bot/webhook`

## API inventory (ключевое)
### Health
- `GET /health`

### Client/WebApp
- `POST /api/client/requests/service`
- `POST /api/client/requests/parts`
- `POST /api/client/requests/consultation`
- `POST /api/client/requests/warranty`
- `POST /api/client/requests/data-change`
- `GET /api/client/requests`
- `GET /api/client/recommendations`
- `POST /api/client/recommendations/:id/interest`

### Integration
- `POST /api/integrations/email`
- `POST /api/integrations/manual`
- `POST /api/integrations/one-c/:entityType`
- `GET /api/integrations/events`
- `GET /api/integrations/events/:id`
- `POST /api/integrations/events/:id/retry`

### Reporting
- `GET /api/reports/summary?period=weekly|monthly|quarterly`
- `GET /api/reports/summary?from=...&to=...`
- `GET /api/reports/requests`
- `GET /api/reports/feedback`
- `GET /api/reports/quality`
- `GET /api/reports/masters`
- `GET /api/reports/sources`
- `GET /api/reports/recommendations`
- `POST /api/reports/snapshots`
- `GET /api/reports/snapshots`
- `GET /api/reports/snapshots/:id`

### WebApp/static
- `GET /`, `/requests`, `/recommendations`
- `GET /forms/service-request`, `/forms/parts-request`, `/forms/consultation`, `/forms/warranty-request`, `/forms/data-change-request`
- `GET /styles.css`, `/webapp.js`

## Smoke-test plan после деплоя
1. `GET /health` -> 200.
2. Вызвать 3 webhook endpoints тестовым update payload.
3. Открыть WebApp страницы `/`, `/requests`, `/recommendations`.
4. Создать минимум 1 client request через API/WebApp.
5. Проверить `GET /api/reports/summary?period=weekly`.
6. Создать snapshot `POST /api/reports/snapshots`.
7. Проверить feedback flow: перевод заявки в `processed` -> task -> клиентская оценка.

## Тесты
```bash
npm test
```
