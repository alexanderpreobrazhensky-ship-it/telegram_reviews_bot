# PROJECT_AUDIT

## 1) Статус этапов
- Skeleton-этап: завершён.
- Этап 2 (client_bot + WebApp MVP): реализован.
- Этап 3 (master_bot MVP): реализован.

## 2) Production contract (BotHost-safe)
- Runtime: Node.js.
- Entrypoint: `app.js`.
- Manifest: `package.json`.
- Ветка деплоя: `main`.
- Node-first запуск сохранён, Python как production path не используется.

## 3) Реализованный master_bot MVP
Webhook:
- `POST /telegram/master_bot/webhook`.

Рабочие сценарии:
- `/start` + главное меню.
- Просмотр новых заявок (`new`).
- Просмотр заявок в работе (`in_progress`).
- Поиск по клиенту: ФИО, телефон, VIN, госномер.
- Карточка клиента.
- Карточка заявки.
- Изменение статуса заявки по разрешённому workflow.
- Добавление внутреннего комментария к заявке.
- Добавление служебной заметки по клиенту (skeleton).
- Просмотр quality cases / карточки quality case / смена статуса / комментарий.
- Инициирование запроса клиенту (intent/event + безопасная отправка шаблона при доступном Telegram token).

Роли (структура заложена):
- `master`
- `manager`
- `admin`

## 4) Статусы и workflow заявок
Поддерживаемые статусы:
- `new`
- `waiting_data`
- `in_progress`
- `processed`
- `lost`
- `archived`

Реализованные переходы:
- `new -> waiting_data`
- `new -> in_progress`
- `waiting_data -> in_progress`
- `in_progress -> processed`
- `in_progress -> lost` (обязателен `lostReason`)
- `processed -> archived`
- `lost -> archived`

Каждая смена статуса:
- пишется в БД,
- добавляется в `requestStatusHistory`,
- фиксирует кто/когда/из какого статуса в какой,
- создаёт event в `communicationEvents`,
- создаёт action в `masterActions`.

## 5) Что теперь сохраняется в `data/db.json`
Сохранена совместимость с этапом 2 (Client/Vehicle/Request/CommunicationEvent/Recommendation), добавлены:
- `staffUsers` — сотрудники и роли.
- `requestStatusHistory` — история статусов заявки.
- `requestInternalComments` — внутренние комментарии мастеров.
- `clientInternalNotes` — служебные заметки по клиенту.
- `masterActions` — журнал действий сотрудников.
- `qualityCases` — skeleton сущности quality.
- `qualityCaseComments` — комментарии к quality cases.

В заявке дополнительно используются:
- `assignedMasterId`
- `lostReason`
- `updatedAt`

## 6) Карточки CRM
### Карточка клиента (минимум)
- ФИО
- телефон
- preferred channel
- telegram binding
- список автомобилей
- список обращений
- список рекомендаций
- внутренние заметки

### Карточка заявки (минимум)
- id
- тип
- статус
- источник
- дата/описание
- клиент
- авто
- ответственный мастер
- история статусов
- внутренние комментарии

## 7) Quality case skeleton
Поддержаны статусы quality case:
- `new`, `assigned`, `in_progress`, `resolved`, `unresolved`, `archived`.

Реализовано:
- список cases,
- карточка case,
- изменение статуса,
- комментарий по разбору.

## 8) Сохранность этапа 2
Не сломаны:
- `client_bot` webhook,
- WebApp страницы и API,
- `/health`.

## 9) Тестовое покрытие этапа 3
Добавлены поведенческие node-тесты для master_bot MVP:
- `/start`, главное меню,
- получение списка новых заявок,
- поиск по ФИО/телефону/VIN/госномеру,
- статусные переходы (`new -> waiting_data`, `new -> in_progress`, `in_progress -> processed`, `in_progress -> lost`),
- обязательность lost reason,
- persistence проверки (status history, internal comment, assignment мастера),
- карточка клиента,
- карточка заявки,
- наличие рекомендаций,
- quality case skeleton проверки.

## 10) Текущая готовность платформы
Платформа готова к следующему шагу: расширение CRM-функций сотрудника, усложнение quality flow и подготовка интеграций (включая 1С), при сохранении BotHost-safe Node.js production contract.
