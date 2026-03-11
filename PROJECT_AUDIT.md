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
  5. Дефолтный случайный домен BotHost не является надёжной production-опцией.
  6. По информации поддержки BotHost обновление из Git для дефолтного случайного домена может работать нестабильно.
  7. Для production нужен короткий пользовательский домен вида `вашлогин.bothost.ru`.
- Что уже предотвращено:
  - invalid JSON больше не валит обработчики, даёт `400`;
  - пустая/битая БД поднимается через safe init;
  - stuck tasks re-claimed.

## 5.10 Domain strategy
- Production domain: `вашлогин.bothost.ru`.
- `WEBAPP_URL` должен ссылаться именно на production short domain `вашлогин.bothost.ru`.
- Telegram webhook URLs должны быть завязаны на этот же домен.
- BotFather Menu Button URL должен указывать на этот же домен.
- Дефолтный случайный домен BotHost не использовать как основной production domain.

## 5.11 HTTPS / certificate readiness
- Перед production deploy обязательно проверить, что домен открывается по HTTPS.
- Проверить валидность сертификата (доверенная цепочка, не истёкший сертификат).
- Убедиться в отсутствии ошибок вида `NET::ERR_CERT_AUTHORITY_INVALID`.
- Проверить, что WebApp открывается без browser security warnings.
- Проверить, что Mini App внутри Telegram открывается корректно по HTTPS.

## 5.12 WebApp / Mini App compatibility
- В текущем MVP-контуре WebApp совместим с Telegram Mini App по архитектуре (статический shell + API + Telegram WebApp launch flow).
- Открытие WebApp из `client_bot` должно работать через корректный `WEBAPP_URL`.
- Статика (`/`, `/styles.css`, `/webapp.js`) должна отдаваться корректно в production.
- Формы WebApp должны отправляться успешно и сохранять обращения.
- Mobile layout не должен ломаться на типичных мобильных экранах Telegram WebView.
- Прямое открытие WebApp по HTTPS в браузере должно работать.
- Часть пунктов (UI/UX, mobile layout, поведение внутри Telegram клиента) требует обязательной ручной проверки перед production deploy.

## 5.13 Theme compatibility
- Обязательна проверка light theme.
- Обязательна проверка dark theme.
- В WebApp не должно быть hardcoded color assumptions, приводящих к потере читаемости в одной из тем.
- Финальная manual visual check на совместимость тем обязательна перед production deploy.

## 5.14 Deploy readiness checklist
### До деплоя
- Проверить `main` branch, Node runtime, `app.js` как entrypoint.
- Выставить обязательные ENV и `WEBAPP_URL` на `https://вашлогин.bothost.ru`.
- Убедиться, что путь `DB_FILE_PATH` указывает на persistent volume.
- Использовать короткий пользовательский домен `вашлогин.bothost.ru`, не случайный дефолтный домен BotHost.
- Проверить HTTPS/certificate readiness до настройки webhook и BotFather.
- Локально прогнать `npm test`.

### В панели BotHost
- Main file: `app.js`.
- Runtime: Node.js 18+.
- Env: как минимум `PORT`, 3 Telegram token, `WEBAPP_URL` (`https://вашлогин.bothost.ru`).
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
- Проверить открытие Mini App из `client_bot` и прямое открытие по HTTPS.
- Проверить light/dark theme вручную в Telegram WebView и в браузере.

## 5.15 Known issues / limitations
- One-C остаётся skeleton-интеграцией (нормализация/route без реального sync).
- Отсутствует полноценная RBAC-аутентификация для HTTP API (MVP уровень).
- Нет внешней очереди/БД; файл-хранилище ограничивает горизонтальное масштабирование.
- Reporting — operational MVP без BI/DWH.

## 5.16 Change history (этап 7)
1. Усилен config loader: безопасный parse + clamping env.
2. Усилен HTTP слой: `400` на invalid JSON, валидация обязательных client полей.
3. Усилен storage: safe-read fallback + atomic write, task field migration.
4. Усилен scheduler: stuck-task recovery, configurable batch/attempts/timeout, loop error logging.
5. Добавлены hardening/regression edge-case тесты.
6. Обновлены `README.md` и текущий `PROJECT_AUDIT.md` под deploy readiness.

## Финальный вывод
- Проект готов к production deploy только при одновременном выполнении условий:
  - single-instance deployment;
  - persistent storage для `db.json`;
  - корректные Telegram tokens;
  - корректные webhook paths;
  - использование короткого пользовательского домена `вашлогин.bothost.ru`;
  - валидный HTTPS сертификат без browser security warnings;
  - корректный `WEBAPP_URL` на production short domain;
  - успешный pre-deploy и post-deploy smoke-check (HTTP/static, bots, WebApp/Mini App, reporting, theme).
- Для роста нагрузки нужен следующий шаг: переход с file-db на транзакционное хранилище и выделенная очередь задач.
