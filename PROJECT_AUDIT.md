# PROJECT_AUDIT

## 1) Статус этапов
- Skeleton-этап: завершён.
- Этап 2 (client_bot + WebApp MVP): реализован.

## 2) Production contract (BotHost-safe)
- Runtime: Node.js.
- Entrypoint: `app.js`.
- Manifest: `package.json`.
- Ветка деплоя: `main`.
- Node-first запуск сохранён, Python как production path не используется.

## 3) Реализованный client_bot MVP
- `POST /telegram/client_bot/webhook` обрабатывает `/start`.
- `/start` отправляет приветствие и WebApp launch кнопку (`web_app.url` через `WEBAPP_URL`).
- Реализованы быстрые сценарии в чате:
  - нужна запись/сервис → `service_request`
  - нужны запчасти → `parts_request`
  - вопрос мастеру → `consultation_request`
  - гарантийное обращение → `warranty_request`
  - свяжитесь со мной → `callback_request`
- Для быстрого обращения бот последовательно запрашивает ФИО и телефон.
- После сбора данных создаётся `Request` со статусом `new` и `sourceChannel=telegram_chat`.

## 4) Реализованный WebApp MVP
### Страницы
- `GET /`
- `GET /requests`
- `GET /recommendations`
- `GET /forms/service-request`
- `GET /forms/parts-request`
- `GET /forms/consultation`
- `GET /forms/warranty-request`
- `GET /forms/data-change-request`

### Формы
- Service request → `service_request`
- Parts request → `parts_request`
- Consultation → `consultation_request`
- Warranty request → `warranty_request`
- Data change request → `data_change_request`

### Клиентские разделы
- “Мои обращения” (список типа/статуса/даты/краткого описания).
- “Актуальные рекомендации” (фильтр `status=actual`) + отметка интереса к устранению.

## 5) API слой
- `GET /health`
- `POST /api/client/requests/service`
- `POST /api/client/requests/parts`
- `POST /api/client/requests/consultation`
- `POST /api/client/requests/warranty`
- `POST /api/client/requests/data-change`
- `GET /api/client/requests`
- `GET /api/client/recommendations`
- `POST /api/client/recommendations/:id/interest`
- Telegram webhook сохранён: `POST /telegram/client_bot/webhook`

## 6) Реальное сохранение данных в MVP
Хранилище: `data/db.json` (файловая БД для MVP).

Сохраняются сущности:
- **Client**: ФИО, телефон, telegramId, preferredChannel.
- **Vehicle**: clientId, brand/model/year/vin/plateNumber.
- **Request**: requestType, status=`new`, sourceChannel, description, clientId, vehicleId.
- **CommunicationEvent**: события действий клиента/создания обращения с источником `bot`/`webapp`.

Реализованы связи:
- Client ↔ Vehicle.
- Client ↔ Request.
- Vehicle ↔ Request (когда есть авто-данные).

## 7) Реально работающие request types в этапе 2
- `service_request`
- `parts_request`
- `warranty_request`
- `consultation_request`
- `callback_request`
- `data_change_request`

## 8) Тестовое покрытие этапа
Добавлены/актуализированы node-тесты:
- доступность `/health` и webapp-страниц,
- создание 5 обязательных типов обращений через API,
- bot flow (`/start` + быстрое обращение),
- persistence-проверки: client + vehicle + request + communication event.

## 9) Ограничения, остающиеся после этапа 2
- Нет 1С интеграции и синхронизации мастер-данных.
- Нет подтверждённой идентификации (SMS/OTP).
- Нет расширенного CRM workflow и сложной карточки обращения.
- Нет каналов VK/MAX.
- Нет production-grade SQL persistence (в MVP используется файловое хранилище).

## 10) Итоговая готовность
Проект готов к следующему шагу: расширение мастерского контура и интеграционных сценариев поверх уже работающего intake-потока client_bot + WebApp.
