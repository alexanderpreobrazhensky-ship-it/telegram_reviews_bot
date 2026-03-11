# Единая платформа автосервиса (Node.js / BotHost)

## Этап 5: integration layer MVP + подготовка к 1С
Реализован первый рабочий интеграционный слой, при этом сохранены контуры этапов 2-4 (`client_bot`, `master_bot`, WebApp, feedback/quality flow, `/health`, действующие webhook/API).

## BotHost production contract
- Runtime: Node.js
- Entrypoint: `app.js`
- Manifest: `package.json`
- Ветка деплоя: `main`
- Python не используется как production startup path.

## Запуск
```bash
npm install
npm start
```

## Новые ENV (этап 5)
- `TELEGRAM_INTEGRATION_BOT_TOKEN`
- `ENABLE_INTEGRATION_WORKER` (default `true`)
- `INTEGRATION_RETRY_MAX` (default `3`)
- `INTEGRATION_RETRY_DELAY_SECONDS` (default `60`)
- `ONE_C_SYNC_ENABLED` (default `false`)
- `EMAIL_IMPORT_ENABLED` (default `true`)

Ранее существующие ENV также сохранены (`PORT`, `NODE_ENV`, `DB_FILE_PATH`, `WEBAPP_URL`, `TELEGRAM_CLIENT_BOT_TOKEN`, `TELEGRAM_MASTER_BOT_TOKEN`, `QUEUE_DRIVER`, `ONE_C_WEBHOOK_SECRET`, и т.д.).

## Integration layer MVP
### Pipeline
Введён application-layer pipeline:
- `receiveIntegrationEvent(...)`
- `normalizeIntegrationPayload(...)`
- `processIntegrationEvent(...)`
- `retryIntegrationEvent(...)`
- `markIntegrationEventFailed(...)`

Поток обработки:
1. Внешний payload сохраняется в `integrationEvents` как `received`.
2. Payload нормализуется (`normalizedPayload`, статус `normalized`).
3. Запускается обработка (`processing`) и domain-update.
4. Результат фиксируется как `processed` / `failed` / `ignored`.
5. История шагов пишется в `integrationEventLogs`.

### Source systems
Поддержаны:
- `email` (working MVP)
- `manual_import` (working MVP)
- `one_c` (normalization + processing skeleton)
- `system` (зарезервировано)

### Event types
Добавлены:
- `email_request_received`
- `one_c_client_sync`
- `one_c_vehicle_sync`
- `one_c_visit_sync`
- `one_c_recommendation_sync`
- `manual_request_import`
- `manual_client_sync`
- `manual_recommendation_sync`

## Email ingestion MVP
### Endpoint
- `POST /api/integrations/email`

### Поддерживаемый payload
- `from`
- `subject`
- `body`
- `receivedAt`
- `attachments` (optional metadata)
- `threadId` (optional)

### Что делает
- создаёт `IntegrationEvent`;
- извлекает имя/телефон/VIN/текст обращения (эвристически);
- определяет тип заявки (`service/parts/warranty/consultation`);
- создаёт/находит `Client`;
- создаёт `Request` c `sourceChannel=email`;
- создаёт `CommunicationEvent`;
- проставляет source-of-truth/external-id метаданные.

## Manual import flow
- `POST /api/integrations/manual`

Позволяет вручную подать `sourceSystem`, `eventType`, `rawPayload`, `dedupeKey` для отладки/тестов/импорта.

## 1С skeleton-ready
- `POST /api/integrations/one-c/:entityType` (`client|vehicle|visit|recommendation`)
- Нормализаторы для `one_c_*_sync` определяют expected raw shape, mapping fields, external-id fields и source-of-truth поведение.
- На текущем этапе 1С-события принимаются и нормализуются, затем помечаются `ignored` (skeleton hook).

## Source-of-truth и external IDs foundation
Для сущностей `clients`, `vehicles`, `visits`, `requests`, `recommendations` добавлены поля:
- `externalIds`
- `sourceSystem`
- `sourceOfTruth`
- `lastSyncedAt`
- `localPendingChanges`
- `needsManualReview`

## Integration bot MVP
Webhook:
- `POST /telegram/integration_bot/webhook`

Команды:
- `/start`
- `/events` (последние)
- `/failed`
- `/pending`
- `/stats` (received/processed/failed)
- `/event <id>`
- `/retry <id>`
- `/ignore <id>` (optional)

## Integration API
Новые endpoints:
- `POST /api/integrations/email`
- `POST /api/integrations/manual`
- `POST /api/integrations/one-c/:entityType`
- `GET /api/integrations/events`
- `GET /api/integrations/events/:id`
- `POST /api/integrations/events/:id/retry`

## Что реально работает vs skeleton
### Реально работает
- integration event pipeline;
- email ingestion в заявку + коммуникационное событие;
- manual import flow;
- retry flow для integration event;
- integration_bot monitoring/control команды.

### Skeleton
- production-grade двусторонняя 1С синхронизация;
- автопланировщик интеграционных retry;
- продвинутый merge/conflict UI.

## Тесты
```bash
npm test
```
