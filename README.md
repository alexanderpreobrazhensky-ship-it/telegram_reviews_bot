# Единая платформа автосервиса (Node.js / BotHost)

## Этап 3: master_bot MVP + client_bot/WebApp continuity
Реализован рабочий контур сотрудника без слома intake-потока:
- Telegram `master_bot` (`POST /telegram/master_bot/webhook`) с `/start`, главным меню и обработкой заявок.
- Сценарии сотрудника: новые заявки, заявки в работе, поиск, карточки клиента/заявки, смена статуса, внутренние комментарии, служебные заметки по клиенту.
- Базовая CRM-персистентность в `data/db.json`: assignment мастера, история статусов, lost reason, internal comments, master actions/events.
- Skeleton quality layer: список/карточка quality case, смена статуса, комментарии по разбору.
- Сохранена работа `client_bot` + WebApp MVP из этапа 2.

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

## Master bot MVP: рабочие сценарии
- `/start` + главное меню.
- Просмотр списков заявок: `new`, `in_progress` (базово), поддержка статусов `waiting_data`, `processed`, `lost`, `archived` в service/storage.
- Поиск по ФИО/телефону/VIN/госномеру.
- Карточка клиента: ФИО, телефон, preferred channel, telegram binding, авто, обращения, рекомендации, внутренние заметки.
- Карточка заявки: id, тип, статус, источник, описание, клиент, авто, ответственный мастер, история статусов, внутренние комментарии.
- Изменение статусов с валидным workflow:
  - `new -> waiting_data`
  - `new -> in_progress`
  - `waiting_data -> in_progress`
  - `in_progress -> processed`
  - `in_progress -> lost` (обязательный lost reason)
  - `processed -> archived`
  - `lost -> archived`
- Внутренние комментарии по заявке (не отправляются клиенту).
- Служебные заметки по клиенту (skeleton).
- Запрос уточнения у клиента: фиксация intent/action/event, при доступном Telegram — попытка шаблонной отправки.
- Quality skeleton: просмотр cases, карточка, смена статуса, комментарий.

## Что пока не реализовано
- Интеграция 1С, VK, MAX.
- Полный quality workflow с автоматическим созданием кейсов.
- Полноценный чат-движок мастер-клиент.
- Продвинутая аналитика/AI.
- Production-grade SQL storage (используется файловое хранилище MVP).

## Тесты
```bash
npm test
```
