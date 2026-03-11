# PROJECT_AUDIT

## 0) Executive summary

- Репозиторий содержит **Node-first production path** (`app.js` + `package.json`) и рабочий HTTP/API слой для трёх Telegram-ботов, WebApp, интеграций и отчётности.  
- Фактический runtime в Node работает как **single-process монолит**: HTTP server + webhook handlers + in-process scheduler.  
- Persistence реализован как **локальный JSON store** (`data/db.json` через `DB_FILE_PATH`), без внешней СУБД и без межпроцессных блокировок.  
- Проект близок к MVP deploy на BotHost **при строгом соблюдении ограничений single instance + persistent volume + корректный домен/HTTPS/WEBAPP_URL**.  
- В репозитории есть заметный **doc/code drift в legacy Python/Docker/BotHost конфигурации**, который не соответствует зафиксированному Node production contract.

---

## 1) Repository snapshot

### 1.1 Текущая структура (верхний уровень)

- `app.js` — production entrypoint Node runtime.
- `package.json` — Node manifest, `main: app.js`, `start: node app.js`, `test: node --test ...`.
- `src/` — основной Node-код (server, interfaces, core, infrastructure, integrations).
- `public/` — статика WebApp (`index.html`, `webapp.js`, `styles.css`).
- `data/` — файловая БД (`db.json` создаётся автоматически, `.gitkeep` в репо).
- `tests/node/` — актуальный Node test suite для production path.
- `tests/test_*.py` — legacy Python-тесты, противоречат текущему Node контракту.
- `legacy/` — legacy wrapper на Node, запускающий `python main.py`.
- `audit/` — старые аудиты/артефакты (дублирующие по смыслу текущий файл).
- `README.md` — основной human-facing документ, частично актуален по Node path.
- `Dockerfile` — legacy Python Docker-рантайм (`main.py`), не совпадает с Node-first контрактом.
- `.bothost/entrypoint.conf` — legacy BotHost настройка `main.py`, не совпадает с Node-first контрактом.

### 1.2 Классификация директорий/файлов

**Production-critical (Node path):**
- `app.js`
- `package.json`
- `src/**`
- `public/**`
- `data/**` (runtime state)

**Validation/quality:**
- `tests/node/**`

**Auxiliary / documentation:**
- `README.md`
- `PROJECT_AUDIT.md`
- `audit/**`

**Legacy / not in production Node path:**
- `bots/**`, `services/**`, `shared/*.py`, `tests/test_*.py`
- `legacy/index.js`
- `Dockerfile` (python)
- `.bothost/entrypoint.conf` (python)

---

## 2) Entrypoints and startup chain

### 2.1 Primary production entrypoint

- **Production entrypoint = `app.js`**.
- `package.json` подтверждает `main: "app.js"`, `scripts.start: "node app.js"`.

### 2.2 Secondary / non-production entrypoints

- `legacy/index.js` запускает `python main.py` (legacy wrapper).
- Python файлы (`bots/**`, `services/**`) могут стартовать отдельно, но не участвуют в Node-first production contract.

### 2.3 Internal startup chain (Node)

1. `app.js` вызывает `bootstrap()`.
2. `bootstrap()` загружает конфиг через `loadConfig()`.
3. Создаётся HTTP server через `createServer({ config, logger })`.
4. Создаётся scheduler через `createScheduler(...)` с task handlers.
5. После `server.listen(port)` запускается `scheduler.start()`.
6. При закрытии сервера (`close`) scheduler останавливается (`scheduler.stop()`).

### 2.4 Где что поднимается

- HTTP server: `src/server/index.js` (`http.createServer`).
- Route registry Telegram webhooks: в `createServer` через `registerClientBotRoutes`, `registerMasterBotRoutes`, `registerIntegrationBotRoutes`.
- Scheduler: инициализируется в `app.js`, работает interval loop внутри того же процесса.
- Telegram webhook handlers: `src/interfaces/*_bot/index.js`.

---

## 3) Runtime model

- Модель выполнения: **один Node-процесс**.
- В этом процессе одновременно:
  - HTTP endpoint-ы (API + статика + health);
  - webhook обработчики трёх ботов;
  - in-process scheduler для задач (`tasks` из file DB).
- Отдельного worker-процесса/очереди/брокера нет.
- Integration processing также выполняется inline в HTTP flow (`receiveIntegrationEvent` → `processIntegrationEvent`) и/или вручную через retry endpoints.

**Ограничения модели:**
- Нет distributed locking.
- Нет горизонтальной безопасной многокопийности на текущем file DB.
- Упор на single-instance deployment.

---

## 4) Feature readiness matrix

| Модуль | Статус | Что реально есть |
|---|---|---|
| `client_bot` | **implemented** | Webhook, `/start`, quick request flow, сбор ФИО+телефон, сохранение заявок, приём rating 1..5, авто-feedback linkage. |
| WebApp | **implemented** | SPA-like статика с формами 5 типов заявок, страницы requests/recommendations, вызовы client API. |
| `master_bot` | **implemented** | `/start`, листинги, поиск, карточки клиента/заявки, смена статусов, комментарии, quality-case команды, report-команды с role-check. |
| `integration_bot` | **partially implemented** | Команды просмотра событий, failed/pending/stats, карточка события, retry/ignore; без push-нотификаций и auth hardening. |
| feedback flow | **implemented** | Task `feedback_request`, сообщение клиенту, парсинг оценки, сохранение feedback, эскалация low rating в quality case. |
| quality flow | **partially implemented** | Авто-создание кейсов при низкой оценке + ручное управление статусами/комментами; нет SLA/ownership workflow. |
| scheduler/task layer | **partially implemented** | Планировщик с claim/processing/fail/retry/stuck recovery; без durable queue semantics/locks между инстансами. |
| integration layer | **partially implemented** | Email/manual ingest реально обрабатываются в request; one_c нормализуется, но бизнес-синк пока skeleton/ignored. |
| reporting layer | **implemented** | Метрики requests/feedback/quality/masters/sources/recommendations + snapshots + summary text. |

---

## 5) Full routes inventory

### 5.1 Health
- `GET /health` — liveness + env echo (`ok`, `env`). Обработчик: `src/server/index.js`.

### 5.2 Telegram webhooks
- `POST /telegram/client_bot/webhook` — client bot сценарии. Обработчик: `src/interfaces/client_bot/index.js`.
- `POST /telegram/master_bot/webhook` — master bot сценарии. Обработчик: `src/interfaces/master_bot/index.js`.
- `POST /telegram/integration_bot/webhook` — integration bot команды. Обработчик: `src/interfaces/integration_bot/index.js`.

### 5.3 Client API
- `POST /api/client/requests/service` — создать сервисную заявку.
- `POST /api/client/requests/parts` — создать заявку на запчасти.
- `POST /api/client/requests/consultation` — создать консультационный запрос.
- `POST /api/client/requests/warranty` — создать гарантийный запрос.
- `POST /api/client/requests/data-change` — запрос изменения данных.
- `GET /api/client/requests` — список обращений (filter: `phone`, `telegramId`).
- `GET /api/client/recommendations` — рекомендации (filter: `phone`, `telegramId`).
- `POST /api/client/recommendations/:id/interest` — отметить интерес к рекомендации.

Все в `src/server/index.js`, с persistence через `src/infrastructure/db/index.js`.

### 5.4 Integration API
- `POST /api/integrations/email` — ingest email event.
- `POST /api/integrations/manual` — manual integration event ingest.
- `POST /api/integrations/one-c/:entityType` (`client|vehicle|visit|recommendation`) — one_c placeholder ingest.
- `GET /api/integrations/events` — список integration events.
- `GET /api/integrations/events/:id` — карточка event + logs.
- `POST /api/integrations/events/:id/retry` — ручной retry event.

### 5.5 Reporting API
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

### 5.6 WebApp/static routes
- `GET /styles.css`
- `GET /webapp.js`
- `GET /`
- `GET /requests`
- `GET /recommendations`
- `GET /forms/service-request`
- `GET /forms/parts-request`
- `GET /forms/consultation`
- `GET /forms/warranty-request`
- `GET /forms/data-change-request`

---

## 6) ENV audit

Ниже — **реально используемые переменные Node runtime**.

### 6.1 Обязательные (для полноценного production запуска)

- `PORT` (required at deploy platform level; в коде есть fallback `3000`).  
  Назначение: HTTP listen port.
- `TELEGRAM_CLIENT_BOT_TOKEN` (required для исходящих сообщений client_bot и feedback уведомлений).
- `TELEGRAM_MASTER_BOT_TOKEN` (required для master notifications / bot operations).
- `TELEGRAM_INTEGRATION_BOT_TOKEN` (required для полноценной эксплуатации integration bot).
- `WEBAPP_URL` (критически required для корректного открытия Mini App из client bot).
- `DB_FILE_PATH` (де-факто required для production, чтобы хранить данные в persistent volume).

### 6.2 Рекомендуемые

- `NODE_ENV` — влияет на `/health` env echo, и операционную диагностику.
- `FEEDBACK_REQUEST_DELAY_MINUTES` — delay до отправки запроса оценки.

### 6.3 Optional / feature flags / integration

- `ENABLE_INTEGRATION_WORKER` (в конфиге; в текущем коде worker отдельно не поднимается).
- `ONE_C_SYNC_ENABLED` (флаг-конфиг, сейчас нет полной реализации sync).
- `EMAIL_IMPORT_ENABLED` (конфиг-флаг; ingest endpoint остаётся доступным).
- `ONE_C_WEBHOOK_SECRET` (конфиг, в маршрутизации/валидации сейчас не применён).
- `INTEGRATION_RETRY_MAX` (конфиг, currently не определяет retry policy в event processor).
- `INTEGRATION_RETRY_DELAY_SECONDS` (конфиг, currently не применён в автоматическом scheduler для integration events).

### 6.4 Scheduler/retry env

- `SCHEDULER_INTERVAL_MS`
- `SCHEDULER_BATCH_SIZE`
- `SCHEDULER_MAX_ATTEMPTS`
- `SCHEDULER_STUCK_TIMEOUT_MS`

Используются в `app.js` при создании scheduler.

### 6.5 Legacy env (вне Node production path)

Есть переменные в Python-части (например `CLIENT_TELEGRAM_BOT_TOKEN`, `BOT_PATH_SECRET`, `WEBHOOK_URL` и др. в `tests/test_runtime_behavior.py`), но они относятся к legacy runtime и не определяют поведение Node `app.js`.

---

## 7) Persistence audit

### 7.1 Тип и расположение хранилища

- Файловая JSON-БД: `DB_FILE_PATH` или default `data/db.json`.
- Автосоздание директории/файла + атомарная запись через temp file rename.
- При битом JSON: safe fallback на `makeInitialStore()` (данные теряются, но приложение поднимается).

### 7.2 Реальные коллекции (store keys)

- `clients`
- `vehicles`
- `visits`
- `requests`
- `communicationEvents`
- `integrationEvents`
- `integrationEventLogs`
- `recommendations`
- `staffUsers`
- `requestStatusHistory`
- `requestInternalComments`
- `clientInternalNotes`
- `masterActions`
- `qualityCases`
- `qualityCaseComments`
- `feedback`
- `tasks`
- `reportSnapshots`

### 7.3 Критичные связи сущностей

- `requests.clientId -> clients.id`
- `requests.vehicleId -> vehicles.id`
- `feedback.requestId -> requests.id`
- `qualityCases.feedbackId -> feedback.id`
- `tasks.payload.requestId/clientId -> requests/clients`
- `integrationEventLogs.eventId -> integrationEvents.id`

### 7.4 Поведение на пустой/битой БД

- Пустая БД: инициализируется начальным store (в т.ч. seed recommendations).
- Битая БД: silently заменяется на initial store (возможная потеря исторических данных без recovery).

### 7.5 Риски persistence

- Нет транзакций и блокировок на multi-instance.
- Потенциальные race conditions при конкурентных записях.
- Нет встроенных backup/restore/versioning механизмов.
- Повреждение файла приводит к reset на пустой store.

---

## 8) Scheduler / task audit

### 8.1 Реально существующие task types

- Используются/создаются:
  - `feedback_request` (реально создаётся при переходе заявки в `processed`).
- Предусмотрены handlers, но фактически пустые:
  - `quality_followup`
  - `recommendation_reminder`
  - `maintenance_reminder`

### 8.2 Как запускается scheduler

- Создаётся в `app.js`.
- Стартует после `server.listen`.
- Работает на `setInterval`.
- Останавливается на `server.close`.

### 8.3 Claim/retry semantics

- `claimDueTasks`: переводит `scheduled -> processing`, инкрементит `attemptCount`.
- stuck recovery: `processing` задачи старше `stuckTimeoutMs` возвращаются в `scheduled`.
- `failTask`: backoff по минутам, после `maxAttempts` -> `failed`.
- `completeTask`: фиксирует `completed` и `processedAt`.

### 8.4 Гарантии и пробелы

**Есть:**
- at-least-once внутри одного процесса при перезапусках (через persisted tasks).
- Базовый recovery stuck-задач.

**Нет:**
- Exactly-once.
- Межинстансовая координация.
- Защита от duplicate processing при нескольких runtime копиях.

---

## 9) Bot audit

### 9.1 client_bot

**Что умеет:**
- `/start` + клавиатура + кнопка открытия WebApp.
- Quick-intent по тексту (сервис/запчасти/гарантия/вопрос/callback).
- Мини-диалог: ФИО -> телефон -> создание заявки.
- Приём feedback в формате `1..5 [комментарий]`.

**Связь с WebApp:**
- В `/start` отправляет кнопку `web_app.url = WEBAPP_URL`.

**Какие данные собирает:**
- `fullName`, `phone`, `telegramId`, описание запроса, rating/comment feedback.

### 9.2 master_bot

**Что умеет:**
- `/start`, меню новых/в работе заявок.
- Поиск CRM (`/search`, сценарий "Поиск").
- Карточки клиента/заявки (`/client`, `/request`).
- Статусы заявок (`/set_status`), комментарии (`/comment`, `/client_note`).
- Quality кейсы: list/card/status/comment.
- Отчёты `/report_*` с ограничением ролей manager/admin.

### 9.3 integration_bot

**Что умеет:**
- `/events`, `/failed`, `/pending`, `/stats`, `/event <id>`, `/retry <id>`, `/ignore <id>`.
- Даёт операционный доступ к integration_events.

**Ограничения:**
- Нет полноценной auth модели для webhook source.
- Нет асинхронных уведомлений/подписок.

---

## 10) WebApp audit

### 10.1 Страницы и формы

Страницы:
- `/` (landing)
- `/requests`
- `/recommendations`

Формы:
- `/forms/service-request`
- `/forms/parts-request`
- `/forms/consultation`
- `/forms/warranty-request`
- `/forms/data-change-request`

### 10.2 Какие данные отправляются

Общие: `fullName`, `phone`.  
Опционально: `brand`, `model`, `year`, `vin`, `plateNumber`, `description/question/changeDetails/visitContext`.

### 10.3 Какие API использует WebApp

- `POST /api/client/requests/*`
- `GET /api/client/requests?phone=...`
- `GET /api/client/recommendations`
- `POST /api/client/recommendations/:id/interest`

### 10.4 Как открывается из client_bot

- Через inline button `web_app.url = config.webAppUrl` в `/start`.

### 10.5 Риски WebApp

- Нет Telegram WebApp SDK-интеграции (тема/инициализация/контекст пользователя ограничены).
- Нет auth-привязки пользователя (запросы по phone query, можно подбирать).
- Нет CSRF/rate-limit/hard validation beyond basic required fields.
- Темизация Telegram light/dark не интегрирована программно; только базовый CSS.

### 10.6 Mini App compatibility

- Базово совместимо как HTTPS web page, открываемая через web_app button.
- Полной адаптации под Telegram Mini App API (initData verification, theme params) нет.

---

## 11) Integration layer audit

### 11.1 Source systems (заложены)

- `email`
- `one_c`
- `manual_import`
- `system`

### 11.2 Event types

- `email_request_received`
- `one_c_client_sync`
- `one_c_vehicle_sync`
- `one_c_visit_sync`
- `one_c_recommendation_sync`
- `manual_request_import`
- `manual_client_sync`
- `manual_recommendation_sync`

### 11.3 Pipeline

1. Event создаётся в `integrationEvents` (`received`).
2. `processIntegrationEvent` ставит `processing`.
3. Нормализация payload (`normalized`).
4. Обработка:
   - email/manual request import -> создание client/vehicle/request + communication event.
   - one_c -> пока `ignored` (skeleton).
5. Финал: `processed` или `failed`.
6. Лог каждого шага в `integrationEventLogs`.

### 11.4 Retry

- Ручной retry через API/бот (`retryIntegrationEvent`), перевод в `retry_scheduled` и повторный process.
- Автоматического фонового retry loop для integration events как отдельного воркера нет.

### 11.5 Что реально работает vs skeleton

- **Работает:** email + manual import pipeline в реальные requests.
- **Skeleton only:** one_c business sync (есть контракт и нормализация, но фактически `ignored`).
- Под 1С подготовлены event types, shape mapping, externalIds/source metadata.

---

## 12) Reporting / analytics audit

### 12.1 Реально считаемые метрики

- Requests: total/byType/byStatus/bySourceChannel/bySourceSystem + shares.
- Feedback: total/avg/low rating share.
- Quality: count/byStatus/resolved/unresolved.
- Masters: touched/processed/lost/qualityAssigned/qualityResolved.
- Sources: telegram_chat/webapp/email/manual_import/one_c/other.
- Recommendations: totals/status split/critical count.
- Timing: средние времена до first move/in_progress/processed/feedback task.

### 12.2 Summaries / snapshots

- `buildManagementSummary` формирует структурированный summary + human text.
- Snapshots сохраняются в `reportSnapshots` и доступны по list/get id.

### 12.3 Report endpoints

- Полный набор `GET /api/reports/*` + `POST /api/reports/snapshots` реализован в server.

### 12.4 Ограничения

- Точность зависит от качества данных в file DB.
- Нет BI/DWH, нет длительной истории вне `db.json`.
- Нет продвинутой агрегации на больших объёмах.

---

## 13) Tests audit

### 13.1 Что есть

- Node suite (`tests/node/*.test.js`) покрывает:
  - production path / structure / config;
  - server routes, webhooks;
  - client/master/integration flows;
  - reporting/snapshots;
  - hardening/regression кейсы.
- Python suite (`tests/test_*.py`) покрывает legacy Python app path.

### 13.2 Что покрыто хорошо

- Основные HTTP маршруты Node.
- Базовые бот-сценарии и статусы.
- Интеграционные и reporting MVP сценарии.

### 13.3 Дыры в покрытии

- Нет нагрузочных/конкурентных тестов file DB race conditions.
- Нет e2e тестов Telegram Mini App внутри real Telegram client.
- Нет security-focused тестов (authz, rate limiting, abuse).
- Нет real one_c integration tests (только skeleton behavior).

---

## 14) Documentation audit

### 14.1 README

- В целом отражает Node-first контракт и ключевые маршруты.
- Но в репозитории есть файлы, противоречащие README и контракту (Dockerfile/.bothost legacy python).

### 14.2 Audit consistency

- Старые файлы в `audit/` дублируют часть информации и могут вводить в заблуждение относительно актуального состояния.
- Единым актуальным документом должен считаться текущий `PROJECT_AUDIT.md`.

### 14.3 Doc/code drift (ключевые несоответствия)

1. **Node production contract vs Dockerfile**: Dockerfile запускает `python main.py`.
2. **Node production contract vs .bothost/entrypoint.conf**: указано `main.py`.
3. **Node tests vs Python tests**: Python tests утверждают отсутствие `app.js/package.json` в корне, что прямо конфликтует с текущим состоянием.

---

## 15) Deploy readiness audit

### 15.1 Что необходимо для деплоя

- Runtime: Node.js 18+
- Entrypoint: `app.js`
- Корректные ENV (минимум: `PORT`, 3 Telegram token, `WEBAPP_URL`, `DB_FILE_PATH`)
- Persistent storage для `DB_FILE_PATH`
- HTTPS-домен для WebApp и webhook

### 15.2 Обязательные условия

- **single-instance deployment** (текущая архитектура не для горизонтали).
- Постоянный volume для JSON DB.
- `WEBAPP_URL` = публичный HTTPS-домен приложения.
- Webhook URL каждого бота должен указывать на тот же production домен.

### 15.3 Что критично до запуска

- Проверить валидность сертификата HTTPS.
- Установить webhook-и и проверить `getWebhookInfo` у всех ботов.
- Проверить доступность `/health`, `/`, `/webapp.js`, `/styles.css`.

### 15.4 Что критично после запуска

- Смоук сценарии ботов (`/start`, создание заявок, feedback, master команды).
- Проверка snapshot/report endpoints.
- Мониторинг роста `db.json`, failed tasks, failed integration events.

---

## 16) BotHost-specific risk audit

- Риск использования случайного дефолтного домена BotHost: нестабильный production anchor для внешних интеграций и BotFather конфигурации.
- Для production нужен короткий пользовательский домен формата `вашлогин.bothost.ru`.
- Этот домен должен использоваться одновременно для:
  - `WEBAPP_URL`
  - Telegram webhook URL (всех 3 ботов)
  - BotFather Menu Button URL
- Случайный дефолтный домен не должен считаться постоянной production-основой.

---

## 17) Known issues / limitations

1. One-C интеграция — skeleton (данные принимаются/нормализуются, но не синхронизируются в полноценный доменный цикл).
2. File DB без межпроцессных lock-ов: риск race/duplicate при multi-instance.
3. Отсутствие полноценной auth/authz модели для HTTP API и webhook hardening.
4. WebApp без Telegram initData verification и без защищённой идентификации пользователя.
5. Legacy Python/Docker/BotHost файлы создают операционный риск ошибочного деплоя не в Node path.
6. Нет полноценной observability (метрики/алерты/трейсинг) на production уровне.

---

## 18) Final deploy conclusion

**Проект готов к MVP-deploy при выполнении обязательных условий, но не готов к масштабируемому production без доработок.**

### MVP-deploy: да, при условиях

Обязательно одновременно:
1. Node runtime (`app.js`) как единственный production entrypoint.
2. Single-instance запуск.
3. Persistent volume для `DB_FILE_PATH`.
4. Валидный HTTPS-домен `вашлогин.bothost.ru`.
5. `WEBAPP_URL` + webhook + BotFather Menu Button на этом домене.
6. Корректные Telegram токены и успешный post-deploy smoke.

### Что остаётся риском даже после MVP запуска

- Ограничения file DB и in-process scheduler при росте нагрузки.
- Отсутствие строгой security perimeter (authN/authZ/rate-limit).
- Недореализованный one_c production sync.
- Doc/code drift в legacy-файлах, способный привести к неправильной конфигурации CI/CD и BotHost.

