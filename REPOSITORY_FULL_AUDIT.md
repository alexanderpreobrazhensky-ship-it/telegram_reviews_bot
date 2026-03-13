# REPOSITORY_FULL_AUDIT.md

Полный итоговый аудит текущего состояния репозитория (Node-first, BotHost target).

## 1. Production contract
- Runtime: Node.js (`package.json`, engine >=18).
- Entrypoint: `app.js` (`package.json.main`, Docker CMD, `.bothost/entrypoint.conf`).
- Manifest/lock: `package.json` + `package-lock.json`.
- BotHost: `main_file=app.js`, `branch=main`.
- Port contract: runtime читает `process.env.PORT` с fallback `3000`.

## 2. Entrypoints and startup chain
1. `node app.js`.
2. `loadConfig()` читает ENV.
3. `createServer()` регистрирует static/API/webhook routes.
4. `createScheduler()` инициализируется в `app.js`.
5. После `listen` запускается scheduler loop.

## 3. Runtime model
- Один Node-процесс: HTTP + webhooks + scheduler.
- Persistence: file DB JSON (`DB_FILE_PATH` или `data/db.json`).
- Отдельный integration worker отсутствует.

## 4. Repository snapshot
- Актуальный production контур: `app.js`, `src/**`, `public/**`, `.bothost/`, `Dockerfile`, `package*.json`.
- Тестовый контур: `tests/node/**` (+ legacy python tests в `tests/test_*.py`).
- Legacy/исторический контур: `bots/**`, `services/**`, `shared/**`, `requirements.txt`, `legacy/index.js`.

## 5. Route inventory
- Health/static: `/health`, `/`, `/styles.css`, `/webapp.js`, `/requests`, `/recommendations`, формы `/forms/*`.
- Client API: `/api/client/requests*`, `/api/client/recommendations*`.
- Integration API: `/api/integrations/email|manual|one-c/*`, `/api/integrations/events*`.
- Reporting API: `/api/reports/*`, snapshots routes.
- Webhooks: `/telegram/client_bot/webhook`, `/telegram/master_bot/webhook`, `/telegram/integration_bot/webhook`.

## 6. Bot audit
- Client bot (Node): webhook handler + WebApp button + outbound notifications.
- Master bot (Node): role/статусы/карточки/quality/reporting команды.
- Integration bot (Node): операторские команды по integration events.
- В проекте есть legacy Python client bot с отдельным ENV-контуром.

## 7. WebApp audit
- `public/index.html`, `public/webapp.js`, `public/styles.css`.
- Канал-инъекция: `WEBAPP_TELEGRAM_CHANNEL_LINK` через серверный script-inject.
- Theme-переменные Telegram Mini App явно не используются (нужен ручной smoke check).

## 8. Persistence audit
- Основа: `src/infrastructure/db/index.js` (JSON file store, auto-init, migrations-lite).
- Критичный параметр: `DB_FILE_PATH`.
- `DB_URL` есть только как декларативный хвост (неактивный SQL runtime).

## 9. Scheduler/task audit
- Scheduler в `app.js` + `src/infrastructure/scheduler/index.js`.
- Параметры через `SCHEDULER_*` + `FEEDBACK_REQUEST_DELAY_MINUTES`.
- Retry/stuck recovery реализованы на file DB task queue.

## 10. Integration layer audit
- Manual/email/one-c endpoints есть.
- `ONE_C_WEBHOOK_SECRET` в config читается, но route-валидация не найдена.
- `ENABLE_INTEGRATION_WORKER`/`ONE_C_SYNC_ENABLED` декларативны для текущей модели.

## 11. Reporting audit
- Доступны summary/requests/feedback/quality/masters/sources/recommendations + snapshots.
- Отдельных reporting-specific ENV в Node runtime не обнаружено.

## 12. Tests audit
- Node tests запускаются `npm test`.
- CI workflow: `npm ci` + `npm test`.
- Присутствуют legacy Python tests, но production-path Node-first.

## 13. Documentation audit
- README корректно фиксирует Node-first/BotHost базовый контракт.
- Есть doc/code drift по части legacy/declarative ENV (см. ENV audit раздел).
- Старые файлы в `audit/*` использовать как вспомогательные, не как source-of-truth.

## 14. Deploy readiness audit
- К deploy готов базовый Node runtime и entrypoint chain.
- Критично заполнить production ENV из `DEPLOY_ENV_REFERENCE.md`.
- Риски: file DB single-process, отсутствует внешняя очередь/БД транзакционного класса.

## 15. BotHost-specific audit
- `.bothost/entrypoint.conf` совпадает с контрактом (`app.js`, `main`).
- Для BotHost минимально: 3 telegram token + `WEBAPP_URL` + `MASTER_BOT_ADMIN_IDS` (+ persistent `DB_FILE_PATH`).
- `PORT` ожидается от платформы.

## 16. Full ENV audit
- Полный список и статусы (`required/recommended/optional/legacy/dead`) вынесены в `DEPLOY_ENV_REFERENCE.md`.
- Разделены Node production path и legacy Python contour.

## 17. Risks and limitations
- Single-process + file DB: ограничения масштабирования и согласованности при multi-instance.
- Декларативные ENV могут вводить в заблуждение (documented-only, без runtime-эффекта).
- Нужен ручной post-deploy smoke check webhooks/WebApp/roles.

## 18. Final deploy conclusion
- Репозиторий подтверждён как Node-first для BotHost.
- Для практической настройки использовать `DEPLOY_ENV_REFERENCE.md` как основной чеклист ENV.
- Перед релизом выполнить smoke:
  1) `/health`, 2) static/WebApp, 3) 3 webhook endpoints, 4) master/admin доступ, 5) reports/snapshots, 6) scheduler side-effects.

## Doc/code drift summary
- Реально обязательные ENV: `PORT` (контракт порта), practically-required для полного бизнеса: `TELEGRAM_CLIENT_BOT_TOKEN`, `TELEGRAM_MASTER_BOT_TOKEN`, `TELEGRAM_INTEGRATION_BOT_TOKEN`, `MASTER_BOT_ADMIN_IDS`, `WEBAPP_URL`.
- ENV для удобства/тюнинга: `DB_FILE_PATH`, `TELEGRAM_MASTERS_CHAT_ID`, `WEBAPP_TELEGRAM_CHANNEL_LINK`, `SCHEDULER_*`, `FEEDBACK_REQUEST_DELAY_MINUTES`, `WEBAPP_DEDUPE_WINDOW_MS`.
- Мёртвые/декларативные: `DB_URL`, `QUEUE_DRIVER`, `ENABLE_INTEGRATION_WORKER`, `ONE_C_SYNC_ENABLED`, `EMAIL_IMPORT_ENABLED`, `ONE_C_WEBHOOK_SECRET`, `INTEGRATION_RETRY_*`.
- Ручной post-deploy smoke check обязателен для Mini App, webhook delivery и role/access flow.
