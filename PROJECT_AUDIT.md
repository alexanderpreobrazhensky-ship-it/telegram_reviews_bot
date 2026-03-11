# PROJECT_AUDIT

## 1) Статус этапов
- Skeleton-этап: завершён.
- Этап 2 (client_bot + WebApp MVP): сохранён рабочим.
- Этап 3 (master_bot MVP): сохранён рабочим.
- Этап 4 (reminders + feedback + quality flow MVP): сохранён рабочим.
- Этап 5 (integration layer MVP + 1С-ready foundation): реализован.

## 2) Production contract (BotHost-safe)
- Runtime: Node.js.
- Entrypoint: `app.js`.
- Manifest: `package.json`.
- Ветка деплоя: `main`.
- Node-first запуск сохранён, Python как production path не используется.

## 3) Что добавлено в этапе 5

### 3.1 Integration layer MVP
Реализован application-сервис интеграций (`src/core/application/integrationService.js`) с pipeline:
- `receiveIntegrationEvent(...)`
- `normalizeIntegrationPayload(...)`
- `processIntegrationEvent(...)`
- `retryIntegrationEvent(...)`
- `markIntegrationEventFailed(...)`

Статусы integration events:
- `received`
- `normalized`
- `processing`
- `processed`
- `failed`
- `retry_scheduled`
- `ignored`

Модель integration event поддерживает поля:
- `id`
- `sourceSystem`
- `eventType`
- `rawPayload`
- `normalizedPayload`
- `processingStatus`
- `processingAttemptCount`
- `lastError`
- `createdAt`
- `processedAt`
- `relatedEntityType`
- `relatedEntityId`
- `dedupeKey`

### 3.2 Supported source systems
Добавлены source systems:
- `email` (working)
- `manual_import` (working)
- `one_c` (skeleton-ready)
- `system` (reserved)

### 3.3 Event types
Добавлены event types:
- `email_request_received`
- `one_c_client_sync`
- `one_c_vehicle_sync`
- `one_c_visit_sync`
- `one_c_recommendation_sync`
- `manual_request_import`
- `manual_client_sync`
- `manual_recommendation_sync`

### 3.4 Email ingestion MVP
Реализован endpoint `POST /api/integrations/email`.

Входной payload поддерживает:
- `from`
- `subject`
- `body`
- `receivedAt`
- optional `attachments`

Поведение:
1. создаётся `IntegrationEvent`;
2. выполняется нормализация email payload;
3. извлекаются имя/телефон/VIN/текст;
4. эвристически определяется тип заявки;
5. создаётся `Request` (`sourceChannel=email`);
6. создаётся/обновляется `Client`;
7. создаётся `CommunicationEvent`;
8. записываются result/status/history в integration event + logs.

### 3.5 Manual import flow
Реализован endpoint `POST /api/integrations/manual`.

Позволяет вручную создать integration event (source/event type/raw payload/dedupe key), запустить normalizer + processor и использовать поток для тестов/отладки/импорта.

### 3.6 one_c normalization skeleton
Реализован endpoint `POST /api/integrations/one-c/:entityType` (`client|vehicle|visit|recommendation`).

Для каждого one_c типа определены:
- expected raw shape;
- normalized shape;
- mapping fields;
- external id mapping;
- source-of-truth behavior.

На текущем этапе one_c события принимаются и нормализуются, затем помечаются `ignored` как skeleton-хук (без production-grade двусторонней синхронизации).

### 3.7 Source-of-truth + external IDs foundation
Расширены сущности (`clients`, `vehicles`, `visits`, `requests`, `recommendations`) полями:
- `externalIds`
- `sourceSystem`
- `sourceOfTruth`
- `lastSyncedAt`
- `localPendingChanges`
- `needsManualReview`

Добавлен базовый match/dedupe skeleton:
- по `externalIds`
- по телефону
- по ФИО + телефону
- для VIN — в процессе email ingestion по vehicle upsert + metadata

### 3.8 integration_bot MVP
`integration_bot` webhook (`POST /telegram/integration_bot/webhook`) получил команды:
- `/start`
- `/events`
- `/failed`
- `/pending`
- `/stats`
- `/event <id>`
- `/retry <id>`
- `/ignore <id>` (optional)

Реализованы monitoring/control функции:
- просмотр последних событий;
- просмотр failed/pending;
- краткая карточка event;
- ручной retry;
- статистика по статусам.

### 3.9 Retry flow
Для failed integration events реализован ручной retry:
- retry через API (`POST /api/integrations/events/:id/retry`);
- retry через integration_bot (`/retry <id>`);
- увеличение `processingAttemptCount`;
- запись шагов в `integrationEventLogs`.

## 4) Изменения в хранилище `data/db.json`
Добавлены коллекции:
- `integrationEvents`
- `integrationEventLogs`
- `visits` (как отдельная коллекция в store)

Расширены коллекции:
- `clients`
- `vehicles`
- `requests`
- `visits`
- `recommendations`

Поддержка source-of-truth/external IDs включена для foundation-подготовки к 1С.

## 5) Новые/расширенные routes
Сохранены без слома:
- `/health`
- client routes
- master routes
- webapp routes
- существующие webhook routes

Добавлены:
- `POST /api/integrations/email`
- `POST /api/integrations/manual`
- `POST /api/integrations/one-c/:entityType`
- `GET /api/integrations/events`
- `GET /api/integrations/events/:id`
- `POST /api/integrations/events/:id/retry`

## 6) ENV расширение
Добавлены env-параметры:
- `TELEGRAM_INTEGRATION_BOT_TOKEN`
- `ENABLE_INTEGRATION_WORKER`
- `INTEGRATION_RETRY_MAX`
- `INTEGRATION_RETRY_DELAY_SECONDS`
- `ONE_C_SYNC_ENABLED`
- `EMAIL_IMPORT_ENABLED`

## 7) Покрытие тестами этапа 5
Добавлены node-тесты:
- `integration-flow.test.js`
  - receive/normalize/process/processed;
  - fail+retry path;
  - manual import;
  - one_c skeleton path.
- `integration-bot.test.js`
  - `/start`
  - events list
  - failed list
  - event card
  - retry flow
  - stats
- `regression-routes-stage5.test.js`
  - `/health`
  - client/master/integration webhooks живы.

## 8) Что реально работает и что skeleton
### Реально работает
- integration pipeline end-to-end для `email_request_received` и `manual_request_import`;
- создание request/client/communication event из email payload;
- хранение integration event history/logs;
- integration_bot monitoring/control;
- ручной retry flow.

### Skeleton
- production-grade live one_c integration;
- полноценная двусторонняя синхронизация;
- автоматический retry scheduler для integration events;
- UI для manual conflict resolution.
