# PROJECT_AUDIT.md

## 5.1 Executive summary
- Платформа работает как **Node.js BotHost-safe monolith** с единым entrypoint `app.js`, HTTP server на core `http`, файловым persistence (`data/db.json`), Telegram webhook-контуром (client/master/integration), WebApp static shell и API-слоем.
- По факту реализованы и покрыты тестами: `client_bot`, WebApp MVP, `master_bot`, feedback/quality flow, integration layer MVP (email/manual + one_c skeleton), analytics/reporting + snapshots.
- На этапе 7 выполнены hardening-изменения: безопасный парсинг/санитизация env, atomic-write для storage, обработка битого JSON на routes/webhooks, базовая валидация client API payload, защита worker от stuck task recovery + расширенные scheduler параметры.
- Текущее состояние: проект **условно готов к деплою на BotHost** для MVP-нагрузки. Главные оставшиеся риски: файловая БД без межпроцессных lock’ов, отсутствие реальной внешней очереди/dead-letter, best-effort retry/идемпотентность для интеграций.

## 5.2 Production contract
- Runtime: Node.js (`>=18`).
- Entrypoint: `app.js`.
- Manifest: `package.json` (`main: app.js`, `start: node app.js`).
- Branch для деплоя: `main`.
- Expected BotHost behavior:
  - поднимается HTTP сервер и отвечает JSON/HTML/static;
  - принимает Telegram webhooks по фиксированным путям;
  - scheduler стартует в процессе приложения.
- Deploy assumptions:
  - BotHost запускает единственный node-процесс;
  - persistent volume доступен для `data/db.json`;
  - webhook URLs корректно проброшены извне.

## 5.3 Repository snapshot
- Основные entrypoints:
  - `app.js` — bootstrap server + scheduler.
  - `src/server/index.js` — route registry и HTTP handlers.
- Основные модули:
  - `src/interfaces/client_bot` — сценарии client bot.
  - `src/interfaces/master_bot` — сценарии мастера/менеджера.
  - `src/interfaces/integration_bot` — команды integration bot.
  - `src/core/application/*` — use-cases, integration service, reporting service.
  - `src/infrastructure/db` — файловое хранилище и CRUD.
  - `src/infrastructure/scheduler` — worker loop.
- Ключевые директории:
  - `public/` — WebApp shell (`index.html`, `webapp.js`, `styles.css`).
  - `tests/node/` — regression + mvp + analytics + hardening tests.
  - `data/` — runtime state (`db.json`).
  - `legacy/`, `audit/` — не в production path.

## 5.4 Feature readiness matrix
| Модуль | Статус | Комментарий |
|---|---|---|
| client_bot | implemented | `/start`, quick requests, feedback capture, quality trigger работают |
| WebApp | implemented | страницы/формы/API маршруты доступны |
| master_bot | implemented | списки, поиск, карточки, статусы, comments, quality actions |
| feedback flow | implemented | task при `processed`, feedback receive, low-rating escalation |
| quality flow | partially implemented | core lifecycle есть, без продвинутой SLA/automation |
| scheduler/task layer | implemented + risky | есть retry/recovery; риск из-за file-db и single-process assumptions |
| integration layer | partially implemented | email/manual работают, one_c только skeleton |
| reporting layer | implemented | summary/metrics/snapshots + manager/admin access |

## 5.5 Routes inventory
- Health:
  - `GET /health`
- Telegram webhooks:
  - `POST /telegram/client_bot/webhook`
  - `POST /telegram/master_bot/webhook`
  - `POST /telegram/integration_bot/webhook`
- Client API:
  - `POST /api/client/requests/service`
  - `POST /api/client/requests/parts`
  - `POST /api/client/requests/consultation`
  - `POST /api/client/requests/warranty`
  - `POST /api/client/requests/data-change`
  - `GET /api/client/requests`
  - `GET /api/client/recommendations`
  - `POST /api/client/recommendations/:id/interest`
- Integration API:
  - `POST /api/integrations/email`
  - `POST /api/integrations/manual`
  - `POST /api/integrations/one-c/:entityType`
  - `GET /api/integrations/events`
  - `GET /api/integrations/events/:id`
  - `POST /api/integrations/events/:id/retry`
- Reporting API:
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
- WebApp/static:
  - `GET /`, `/requests`, `/recommendations`
  - `GET /forms/service-request`, `/forms/parts-request`, `/forms/consultation`, `/forms/warranty-request`, `/forms/data-change-request`
  - `GET /styles.css`, `/webapp.js`

## 5.6 ENV audit
### Обязательные
- `PORT` (required для BotHost bind): порт HTTP.
- `TELEGRAM_CLIENT_BOT_TOKEN` (required для исходящих client_bot сообщений).
- `TELEGRAM_MASTER_BOT_TOKEN` (required для staff/quality уведомлений).
- `TELEGRAM_INTEGRATION_BOT_TOKEN` (required для integration bot в Telegram).

### Рекомендованные
- `WEBAPP_URL`: корректная кнопка открытия WebApp из client_bot.
- `DB_FILE_PATH`: путь к `db.json` на persistent volume.
- `NODE_ENV`: production/dev профиль логов.

### Optional runtime toggles
- `ENABLE_INTEGRATION_WORKER`
- `ONE_C_SYNC_ENABLED`
- `EMAIL_IMPORT_ENABLED`
- `ONE_C_WEBHOOK_SECRET` (для будущего усиления one_c routes)

### Scheduler / retry env
- `SCHEDULER_INTERVAL_MS` (санитизируется, min 1000)
- `SCHEDULER_BATCH_SIZE`
- `SCHEDULER_MAX_ATTEMPTS`
- `SCHEDULER_STUCK_TIMEOUT_MS`
- `FEEDBACK_REQUEST_DELAY_MINUTES`
- `INTEGRATION_RETRY_MAX`
- `INTEGRATION_RETRY_DELAY_SECONDS`

### Debugging/feature-flags
- Спец debug env отсутствуют; debug ведётся через логи и тестовый payload.

## 5.7 Persistence audit
- Используемые коллекции: `clients`, `vehicles`, `visits`, `requests`, `communicationEvents`, `integrationEvents`, `integrationEventLogs`, `recommendations`, `staffUsers`, `requestStatusHistory`, `requestInternalComments`, `clientInternalNotes`, `masterActions`, `qualityCases`, `qualityCaseComments`, `feedback`, `tasks`, `reportSnapshots`.
- Критичные связи:
  - `request.clientId -> clients.id`
  - `request.vehicleId -> vehicles.id`
  - `feedback.requestId/clientId` + `qualityCase.feedbackId`
  - `tasks.payload.requestId/clientId`
  - `integrationEvents.relatedEntityId`
- Выполненный hardening:
  - safe fallback при битом JSON (инициализация empty store);
  - atomic write через temp-file + rename;
  - миграция полей task (`processingStartedAt`, `updatedAt`).
- Риски `data/db.json`:
  - нет file locking при потенциальном multi-process запуске;
  - полный read/write файла на каждую операцию;
  - при экстремальном размере файла latency вырастет.

## 5.8 Scheduler / worker audit
- Worker цикл: `createScheduler(...).runOnce()` -> claim due tasks -> handler -> complete/fail.
- Task types: `feedback_request`, `quality_followup`, `recommendation_reminder`, `maintenance_reminder`.
- Добавленные усиления:
  - защита от double-run (`running` guard);
  - recovery stuck `processing` tasks по `SCHEDULER_STUCK_TIMEOUT_MS`;
  - конфигурируемые batch/maxAttempts;
  - отдельный лог для loop-level ошибки.
- Риски:
  - exactly-once не гарантируется;
  - retry backoff простой;
  - нет отдельной dead-letter queue.

## 5.9 BotHost deployment risk audit
- Возможные риски:
  1. Не заданы Telegram токены -> исходящие сообщения не уходят.
  2. Не persistent storage для `db.json` -> потеря данных после рестарта.
  3. Неверно выставлены webhook URL/path -> update не доходит.
  4. Деплой нескольких инстансов на shared file-db -> race/consistency проблемы.
- Что уже предотвращено:
  - invalid JSON больше не валит обработчики, даёт `400`;
  - пустая/битая БД поднимается через safe init;
  - stuck tasks re-claimed.

## 5.10 Deploy readiness checklist
### До деплоя
- Проверить `main` branch, Node runtime, `app.js` как entrypoint.
- Выставить обязательные ENV и `WEBAPP_URL`.
- Убедиться, что путь `DB_FILE_PATH` указывает на persistent volume.
- Локально прогнать `npm test`.

### В панели BotHost
- Main file: `app.js`.
- Runtime: Node.js 18+.
- Env: как минимум `PORT`, 3 Telegram token, `WEBAPP_URL`.
- Проверить webhook set на:
  - `/telegram/client_bot/webhook`
  - `/telegram/master_bot/webhook`
  - `/telegram/integration_bot/webhook`

### После запуска
- `GET /health` => `200 { ok: true }`.
- `GET /` + `/styles.css` + `/webapp.js` => 200.
- `GET /api/reports/summary?period=weekly` => 200.
- `POST /api/reports/snapshots` => 201.

### Telegram smoke
- Client bot: `/start`, quick request, feedback `1..5`.
- Master bot: `/start`, list/search, status transitions, lost reason validation.
- Integration bot: `/start`, failed list, retry flow.

### WebApp smoke
- Открыть формы, отправить минимум 1 обращение каждого типа.
- Проверить список обращений и рекомендации.

## 5.11 Known issues / limitations
- One-C остаётся skeleton-интеграцией (нормализация/route без реального sync).
- Отсутствует полноценная RBAC-аутентификация для HTTP API (MVP уровень).
- Нет внешней очереди/БД; файл-хранилище ограничивает горизонтальное масштабирование.
- Reporting — operational MVP без BI/DWH.

## 5.12 Change history (этап 7)
1. Усилен config loader: безопасный parse + clamping env.
2. Усилен HTTP слой: `400` на invalid JSON, валидация обязательных client полей.
3. Усилен storage: safe-read fallback + atomic write, task field migration.
4. Усилен scheduler: stuck-task recovery, configurable batch/attempts/timeout, loop error logging.
5. Добавлены hardening/regression edge-case тесты.
6. Обновлены `README.md` и текущий `PROJECT_AUDIT.md` под deploy readiness.

## Финальный вывод
- Для MVP-эксплуатации на BotHost проект готов при условии single-instance + persistent `db.json` + корректных webhook/env.
- Для роста нагрузки нужен следующий шаг: переход с file-db на транзакционное хранилище и выделенная очередь задач.
