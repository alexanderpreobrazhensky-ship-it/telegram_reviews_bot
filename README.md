# Единая платформа автосервиса (Node.js / BotHost)

## Этап 2: client_bot + WebApp MVP
Реализован рабочий пользовательский контур:
- Telegram `client_bot` с `/start`, кнопкой запуска WebApp и быстрыми обращениями в чате.
- WebApp MVP (dashboard, формы обращений, список обращений, актуальные рекомендации).
- Реальное сохранение данных в локальную БД-файл `data/db.json`.
- Связка Client ↔ Vehicle ↔ Request + фиксация `CommunicationEvent`.

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

## ENV
- `PORT` (default `3000`)
- `NODE_ENV`
- `DB_URL` (зарезервировано под будущую внешнюю БД)
- `DB_FILE_PATH` (опциональный путь к json-хранилищу)
- `WEBAPP_URL` (HTTPS URL для кнопки открытия WebApp из Telegram)
- `TELEGRAM_CLIENT_BOT_TOKEN`
- `TELEGRAM_MASTER_BOT_TOKEN`
- `TELEGRAM_INTEGRATION_BOT_TOKEN`
- `QUEUE_DRIVER`
- `ONE_C_WEBHOOK_SECRET`

## Routes
### Health
- `GET /health`

### WebApp pages
- `GET /`
- `GET /requests`
- `GET /recommendations`
- `GET /forms/service-request`
- `GET /forms/parts-request`
- `GET /forms/consultation`
- `GET /forms/warranty-request`
- `GET /forms/data-change-request`

### API
- `POST /api/client/requests/service`
- `POST /api/client/requests/parts`
- `POST /api/client/requests/consultation`
- `POST /api/client/requests/warranty`
- `POST /api/client/requests/data-change`
- `GET /api/client/requests?phone=...`
- `GET /api/client/recommendations`
- `POST /api/client/recommendations/:id/interest`

### Telegram webhooks
- `POST /telegram/client_bot/webhook`
- `POST /telegram/master_bot/webhook`
- `POST /telegram/integration_bot/webhook`

## Что уже работает
- Создание обращений по типам: `service_request`, `parts_request`, `consultation_request`, `warranty_request`, `data_change_request`, `callback_request` (через быстрый сценарий в боте).
- Для новых обращений статус по умолчанию: `new`.
- Быстрые обращения в Telegram запрашивают ФИО и телефон, сохраняются с `sourceChannel=telegram_chat`.
- WebApp формирует обращения с `sourceChannel=webapp`.
- Клиент может просматривать список своих обращений и актуальные рекомендации.

## Ограничения MVP
- Нет авторизации/SMS-подтверждения.
- Нет интеграции с 1С и внешними каналами VK/MAX.
- Нет сложного workflow статусов, таймлайнов и кабинетного редактирования master-данных.
- Хранилище MVP — json-файл, подготовлено к замене на полноценную БД.

## Тесты
```bash
npm test
```
