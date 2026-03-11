# Единая платформа автосервиса (Node.js / BotHost)

## Production contract (неизменяемый)
- Runtime: **Node.js**
- Entrypoint: **`app.js`**
- Manifest: **`package.json`**
- Deploy branch: **`main`**
- Production path: **Node-first** (Python не участвует в production startup path)

## Что реализовано
- `client_bot` + клиентский Telegram WebApp (Mini App контур).
- `master_bot` MVP.
- `integration_bot` MVP.
- feedback/quality flow MVP.
- integration layer MVP (email/manual + one_c skeleton).
- analytics/reporting MVP + snapshots.
- scheduler/worker для reminders и задач качества.

## Быстрый запуск локально
```bash
npm install
npm start
```

## Deploy on BotHost
1. В BotHost выбрать ветку **`main`**.
2. Runtime: **Node.js 18+**.
3. Main file (entrypoint): **`app.js`**.
4. Прописать ENV (обязательные и рекомендуемые ниже).
5. Назначить `DB_FILE_PATH` на persistent storage (иначе будет потеря данных после рестартов).
6. Проверить и зарегистрировать webhook URL на боевом домене.
7. Выполнить pre/post-deploy checklist из этого README.

## ENV
### Обязательные
- `PORT`
- `TELEGRAM_CLIENT_BOT_TOKEN`
- `TELEGRAM_MASTER_BOT_TOKEN`
- `TELEGRAM_INTEGRATION_BOT_TOKEN`

### Рекомендуемые
- `WEBAPP_URL` — URL Mini App для кнопки в `client_bot`.
- `DB_FILE_PATH` — путь к файловой БД (на BotHost должен быть persistent volume).
- `NODE_ENV=production`

### Optional runtime toggles
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

## Domain strategy (BotHost production)
> Важно: по данным поддержки BotHost дефолтный случайный домен сейчас ненадёжен для production (наблюдается нестабильность git-update).

Используйте как production-базу короткий пользовательский домен:
- **`вашлогин.bothost.ru`**

Этот домен должен использоваться единообразно для:
- `WEBAPP_URL`
- `setWebhook` URL для всех 3 ботов
- BotFather Menu Button URL
- smoke tests и ежедневной эксплуатации

Перед настройкой BotFather и webhook обязательно проверить:
- сертификат валиден
- HTTPS открывается без warning
- отсутствует ошибка вида `NET::ERR_CERT_AUTHORITY_INVALID`

## Telegram / BotFather
1. В BotFather для `client_bot` установить Menu Button URL на `https://вашлогин.bothost.ru/`.
2. `WEBAPP_URL` в ENV должен указывать на тот же домен.
3. Webhook для всех ботов строится на том же домене:
   - `https://вашлогин.bothost.ru/telegram/client_bot/webhook`
   - `https://вашлогин.bothost.ru/telegram/master_bot/webhook`
   - `https://вашлогин.bothost.ru/telegram/integration_bot/webhook`
4. После деплоя проверить `getWebhookInfo` у каждого бота.

## Webhook routes
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

## Pre-deploy checklist
1. `main` branch выбран в BotHost.
2. Runtime = Node.js.
3. Entrypoint = `app.js`.
4. Все обязательные ENV заданы.
5. `WEBAPP_URL` указывает на короткий пользовательский домен.
6. `DB_FILE_PATH` указывает на persistent storage.
7. `/styles.css` и `/webapp.js` доступны.
8. Theme-совместимость WebApp проверена (light/dark).
9. Webhook URL/path проверены для всех ботов.

## Post-deploy checklist
1. `GET /health`.
2. `GET /`.
3. `GET /styles.css`.
4. `GET /webapp.js`.
5. `GET /api/reports/summary?period=weekly`.
6. `POST /api/reports/snapshots`.
7. WebApp открывается напрямую по HTTPS.
8. WebApp открывается из `client_bot`.
9. `client_bot` отвечает на `/start`.
10. `master_bot` отвечает на `/start`.
11. `integration_bot` отвечает на `/start`.
12. Webhook зарегистрирован и обновления приходят.
13. Интерфейс не ломается в light/dark теме Telegram.

## Smoke tests (ручные)
1. Проверить health и выдачу статики (`/`, `/styles.css`, `/webapp.js`).
2. Открыть WebApp на мобильном экране Telegram и напрямую по URL.
3. Пройти форму создания заявки (минимум один тип), проверить отображение результата.
4. Проверить разделы `Мои обращения` и `Рекомендации`.
5. Проверить `/start` в `client_bot`, `master_bot`, `integration_bot`.
6. Проверить reporting endpoint и snapshot creation.
7. Пройти feedback flow (создание заявки -> `processed` -> оценка).
8. Проверить тему: фон, текст, кнопки, формы, границы, карточки.

## Domain/certificate отдельная проверка
- Назначен короткий пользовательский домен `вашлогин.bothost.ru`.
- SSL сертификат валиден.
- Нет `NET::ERR_CERT_AUTHORITY_INVALID`.
- Mini App открывается без security warning.

## Тесты
```bash
npm test
```
