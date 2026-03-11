# PROJECT_AUDIT.md — final pre-deploy re-audit

## 9.1 Executive summary
Проект — единая Node.js-платформа автосервиса с тремя Telegram-ботами (`client_bot`, `master_bot`, `integration_bot`), WebApp, integration/event pipeline, scheduler и reporting-слоем. Production-контракт зафиксирован как Node-first и синхронизирован с deploy-конфигами. Ключевые блокеры деплоя закрыты: lockfile для `npm ci` и runtime-port через `process.env.PORT` (с local fallback 3000). Риски MVP-уровня остаются в зоне file DB, single-process scheduler и skeleton one_c integration.

## 9.2 Production contract
- Runtime: **Node.js**
- Entrypoint: **`app.js`**
- Manifest: **`package.json`**
- Branch: **`main`**
- Platform target: **BotHost**
- Production path: **Node-first**

## 9.3 Repository snapshot
### Production-critical
- `app.js`
- `src/server/index.js`
- `src/interfaces/*`
- `src/core/*`
- `src/infrastructure/*`
- `public/*`
- `package.json`, `package-lock.json`
- `.bothost/entrypoint.conf`
- `Dockerfile`

### Auxiliary
- `tests/node/*` — актуальные Node tests.
- `audit/*` — старые audit artifacts (не являются source of truth).

### Legacy
- `bots/*`, `services/*`, `shared/*`, `tests/test_*.py`, `requirements.txt`, `legacy/index.js` — historical Python/transition contour, не production path.

## 9.4 Entrypoints and startup chain
1. `node app.js` → `bootstrap()`.
2. `loadConfig()` из `src/infrastructure/config/index.js`.
3. `createServer()` из `src/server/index.js`.
4. Регистрация webhook-роутов из:
   - `src/interfaces/client_bot/index.js`
   - `src/interfaces/master_bot/index.js`
   - `src/interfaces/integration_bot/index.js`
5. Инициализация scheduler через `createScheduler()`.
6. `server.listen(config.port)`; `config.port` = `process.env.PORT` (fallback 3000 local only); startup log отражает фактический runtime port.

## 9.5 Runtime model
- Single Node process.
- HTTP server обслуживает API + webhooks + static WebApp.
- Scheduler работает как interval-loop в том же процессе.
- Persistence: file JSON DB (`DB_FILE_PATH`).
- Ограничения: нет distributed locking, нет external queue/exactly-once гарантий.

## 9.6 Feature readiness matrix
- `client_bot` — **implemented (MVP)**.
- WebApp — **implemented (MVP)**.
- `master_bot` — **implemented (MVP)**.
- `integration_bot` — **implemented (MVP/operator tool)**.
- feedback flow — **implemented**.
- quality flow — **partially implemented**.
- scheduler/task layer — **implemented with operational limits**.
- integration layer — **implemented (email/manual) + one_c skeleton**.
- reporting layer — **implemented (summary + metrics + snapshots)**.

## 9.7 Full routes inventory
### Health
- `GET /health` — сервисный health-check.

### Telegram webhooks
- `POST /telegram/client_bot/webhook` — входящие обновления client bot.
- `POST /telegram/master_bot/webhook` — команды мастер/менеджер бота.
- `POST /telegram/integration_bot/webhook` — мониторинг integration events.

### Client API
- `POST /api/client/requests/service`
- `POST /api/client/requests/parts`
- `POST /api/client/requests/consultation`
- `POST /api/client/requests/warranty`
- `POST /api/client/requests/data-change`
- `GET /api/client/requests`
- `GET /api/client/recommendations`
- `POST /api/client/recommendations/:id/interest`

### Integration API
- `POST /api/integrations/email`
- `POST /api/integrations/manual`
- `POST /api/integrations/one-c/:entityType`
- `GET /api/integrations/events`
- `GET /api/integrations/events/:id`
- `POST /api/integrations/events/:id/retry`

### Reporting API
- `GET /api/reports/summary`
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
- `GET /`
- `GET /requests`
- `GET /recommendations`
- `GET /forms/service-request`
- `GET /forms/parts-request`
- `GET /forms/consultation`
- `GET /forms/warranty-request`
- `GET /forms/data-change-request`
- `GET /styles.css`
- `GET /webapp.js`

## 9.8 ENV audit
### Обязательные
- `PORT` — runtime listening port (обязателен для production, передаётся платформой).
- `TELEGRAM_CLIENT_BOT_TOKEN` — отправка/обработка client bot.
- `TELEGRAM_MASTER_BOT_TOKEN` — master bot webhook/ответы.
- `TELEGRAM_INTEGRATION_BOT_TOKEN` — integration bot webhook/ответы.

### Рекомендуемые
- `WEBAPP_URL` — ссылка Mini App.
- `DB_FILE_PATH` — путь к persistent file DB.
- `NODE_ENV` — окружение.

### Optional
- `DB_URL` (в конфиге, сейчас не драйвит file DB runtime).
- `QUEUE_DRIVER` (memory by default).

### Scheduler/retry
- `SCHEDULER_INTERVAL_MS`
- `SCHEDULER_BATCH_SIZE`
- `SCHEDULER_MAX_ATTEMPTS`
- `SCHEDULER_STUCK_TIMEOUT_MS`
- `FEEDBACK_REQUEST_DELAY_MINUTES`
- `INTEGRATION_RETRY_MAX`
- `INTEGRATION_RETRY_DELAY_SECONDS`

### Integration-related
- `ENABLE_INTEGRATION_WORKER`
- `ONE_C_SYNC_ENABLED`
- `EMAIL_IMPORT_ENABLED`
- `ONE_C_WEBHOOK_SECRET`

### Deploy-related
- `PORT`, `WEBAPP_URL`, `DB_FILE_PATH`, `NODE_ENV`.

## 9.9 Persistence audit
- Хранилище: JSON file DB (`src/infrastructure/db/index.js`).
- Коллекции: clients, vehicles, visits, requests, communicationEvents, integrationEvents, integrationEventLogs, recommendations, staffUsers, requestStatusHistory, requestInternalComments, clientInternalNotes, masterActions, qualityCases, qualityCaseComments, feedback, tasks, reportSnapshots.
- При пустой/битой БД происходит auto-init структуры.
- Риски: race conditions при многопроцессном доступе, размер файла, отсутствие транзакций.

## 9.10 Scheduler / task audit
- Task types в runtime: `feedback_request`, `quality_followup`, `recommendation_reminder`, `maintenance_reminder`.
- Запуск: при старте `app.js` после `server.listen`.
- Retries: через `failTask(..., maxAttempts)`.
- Stuck recovery: `claimDueTasks({ stuckTimeoutMs })`.
- Ограничения: at-least-once, без exactly-once и без distributed coordination.

## 9.11 Bot audit
- `client_bot`: `/start`, быстрые обращения, сбор feedback (1..5 + комментарий), webapp deep-link.
- `master_bot`: команды по заявкам/клиентам/quality/reporting, role-based доступ.
- `integration_bot`: команды мониторинга integration events (`/events`, `/failed`, `/pending`, `/stats`, `/event`, `/retry`, `/ignore`).

## 9.12 WebApp audit
- Single-page WebApp (`public/index.html`, `public/webapp.js`, `public/styles.css`).
- Формы создают обращения через `/api/client/requests/*`.
- Страницы истории/рекомендаций используют `/api/client/requests` и `/api/client/recommendations`.
- Mini App flow: открытие из Telegram через `WEBAPP_URL`.
- Ограничения: ручная проверка поведения внутри Telegram-клиентов обязательна.

## 9.13 Theme compatibility
- Поддержка light/dark должна проверяться вручную.
- Есть риск hardcoded цветов (MVP front без автоматизированного visual regression).

## 9.14 Integration layer audit
- Source systems: `email`, `manual_import`, `one_c`.
- Event types: manual import и one_c sync типы.
- Pipeline: receive → normalize/process → status/retry.
- Retry flow: `POST /api/integrations/events/:id/retry` + policy в сервисе.
- Working: email/manual.
- Skeleton/risky: полноценный one_c sync.

## 9.15 Reporting / analytics audit
- Метрики: requests, feedback, quality, masters, sources, recommendations, timing.
- Summary: `GET /api/reports/summary` + форматированный summary text.
- Snapshots: `POST/GET /api/reports/snapshots`.
- Ограничения: качество отчёта зависит от полноты входных событий (особенно visits/one_c).

## 9.16 Tests audit
- Актуальные: `tests/node/*` (Node runtime, routes, flows, reporting, hardening).
- Legacy Python tests изолированы как historical-only (marked `@unittest.skip`).
- Непокрыто: e2e Mini App в Telegram клиентах, real BotFather/webhook infra, production SSL.

## 9.17 Documentation audit
- README синхронизирован с Node-first production contract.
- Устранён doc/code drift по Dockerfile, entrypoint и CI runtime.
- Legacy traces сохранены только как historical контур и не определяют deploy narrative.

## 9.18 BotHost-specific risk audit
- Дефолтный случайный BotHost домен не рассматривать как надёжную production-базу.
- По operational практике update-from-git для такого домена может быть нестабилен.
- Production domain: `вашлогин.bothost.ru`.

## 9.19 Domain strategy
- Использовать единый домен `https://вашлогин.bothost.ru`.
- Он обязателен для `WEBAPP_URL`, webhook URLs и BotFather menu button.
- Это снижает риск drift между каналами и улучшает воспроизводимость deploy.

## 9.20 HTTPS / certificate readiness
Проверить перед production:
1. Корректный сертификат на `вашлогин.bothost.ru`.
2. Нет `NET::ERR_CERT_AUTHORITY_INVALID`.
3. Нет browser security warnings.
4. Mini App открывается по HTTPS из Telegram.

## 9.21 Deploy readiness audit
### Pre-deploy
- `npm ci` проходит и не требует fallback на `npm install`.
- `npm test` проходит.
- `.bothost/entrypoint.conf` указывает `app.js`.
- Dockerfile согласован с Node runtime.

### BotHost assumptions
- Branch `main`.
- Runtime Node.js.
- Main file `app.js`.
- ENV заданы (`PORT`, токены, `WEBAPP_URL`, `DB_FILE_PATH`).

### Post-deploy smoke
- `/health`, `/`, `/styles.css`, `/webapp.js`.
- Webhooks 3 ботов.
- WebApp submit/list flows.
- Reporting endpoints.

## 9.22 Known issues / limitations
- File DB не рассчитана на высокую конкурентность.
- Scheduler single-process.
- one_c интеграция частично skeleton.
- Нет полного e2e набора с Telegram/HTTPS инфраструктурой.

## 9.23 Final deploy conclusion
Репозиторий **готов к MVP deploy операционно безопасно при условиях**:
1. Используется Node-first контракт (`app.js`, `package.json`, `main`).
2. Настроен production-домен `вашлогин.bothost.ru`.
3. Заданы обязательные ENV и persistent `DB_FILE_PATH`.
4. Пройден post-deploy smoke checklist.

Оставшиеся риски являются типичными для MVP и не блокируют запуск при соблюдении условий выше.
