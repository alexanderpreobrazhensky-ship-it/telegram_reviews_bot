# PROJECT_AUDIT

## 1) Краткое описание проекта
Единая Node.js-платформа автосервиса с разделением на клиентский, мастерский и интеграционный контуры и WebApp как основной UX слой.

## 2) Production contract
- Runtime: Node.js (BotHost-safe)
- Main branch: `main`
- Root entrypoint: `app.js`
- Package manifest: `package.json`
- Legacy Python path исключён из production startup contract

## 3) Текущая архитектура
- `core`: domain + application + shared
- `interfaces`: client_bot, master_bot, integration_bot, webapp
- `integrations`: email, one_c placeholders
- `infrastructure`: config, logging, db, queue, scheduler, repositories
- `server`: HTTP shell for health/webhooks/webapp delivery

## 4) Структура репозитория (актуальная)
- `app.js`
- `package.json`
- `README.md`
- `PROJECT_AUDIT.md`
- `src/`
- `public/`
- `tests/node/`

## 5) Список сервисов
- `client_bot`: клиентский Telegram интерфейс + связка с WebApp
- `master_bot`: рабочий Telegram интерфейс мастера/приёмщика
- `integration_bot`: integration-facing контур и pipeline hooks

## 6) Список сущностей
- Client
- ChannelAccount
- Vehicle
- Request
- Visit
- Recommendation
- PartRequest
- Feedback
- QualityCase
- CommunicationEvent
- Task
- IntegrationEvent

## 7) Согласованные типы и статусы
### Request types
- `service_request`
- `parts_request`
- `warranty_request`
- `complaint_request`
- `feedback_request`
- `consultation_request`
- `callback_request`
- `data_change_request`
- `other_request`

### Request statuses
- `new`
- `waiting_data`
- `in_progress`
- `processed`
- `lost`
- `archived`

### Visit statuses
- `scheduled`
- `in_service`
- `completed`
- `cancelled`
- `no_show`
- `closed`

Visit flags:
- `is_repeat`
- `is_warranty`
- `is_promo`

### Recommendation statuses
- `actual`
- `completed`
- `declined`
- `expired`
- `deleted`

Recommendation severity:
- `normal`
- `critical`

### Quality case statuses
- `new`
- `assigned`
- `in_progress`
- `resolved`
- `unresolved`
- `archived`

## 8) Текущие ENV переменные
- PORT
- NODE_ENV
- DB_URL
- QUEUE_DRIVER
- TELEGRAM_CLIENT_BOT_TOKEN
- TELEGRAM_MASTER_BOT_TOKEN
- TELEGRAM_INTEGRATION_BOT_TOKEN
- ONE_C_WEBHOOK_SECRET

## 9) Текущие маршруты / entrypoints
Entrypoint:
- `app.js`

Health:
- `GET /health`

Webhooks:
- `POST /telegram/client_bot/webhook`
- `POST /telegram/master_bot/webhook`
- `POST /telegram/integration_bot/webhook`

WebApp routes:
- `/`
- `/requests`
- `/recommendations`
- `/forms/service-request`
- `/forms/parts-request`
- `/forms/consultation`
- `/forms/warranty-request`
- `/forms/data-change-request`

## 10) Текущий статус реализации
Skeleton-этап завершён: зафиксирована архитектура, доменные типы и инфраструктурные каркасы. Реализация бизнес-процессов отложена на следующие этапы.

## 11) Change history (последняя задача)
- Добавлен Node.js root entrypoint и package contract для BotHost.
- Создана модульная структура `core/interfaces/integrations/infrastructure/server`.
- Зафиксированы сущности, связи, source-of-truth поля и integration hooks.
- Добавлен WebApp skeleton в `public` и routing/state заготовки.
- Добавлены structural tests для архитектурного каркаса.
