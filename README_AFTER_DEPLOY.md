# README_AFTER_DEPLOY

## Архитектура после разделения

- `services/client_bot_service` — клиентский бот, intake заявок, WebApp, мастер-чат, pin-flow.
- `services/reviews_bot_service` — бот отзывов.
- Оба сервиса используют **единую картотеку клиентов**: `./clients.jsonl` в корне репозитория (можно переопределить `CLIENTS_REGISTRY_PATH`).

```text
.
├─ clients.jsonl                  # единая картотека для client+reviews
├─ services/
│  ├─ client_bot_service/
│  └─ reviews_bot_service/
├─ shared/
│  └─ clients_registry.py         # общий stdlib-модуль обновления картотеки
└─ data/
   ├─ tickets.jsonl
   └─ system.json
```

## ENV (без опасных fallback)

### client_bot_service
- `CLIENT_TELEGRAM_BOT_TOKEN` — обязательный токен клиентского бота (только этот env).
- `CLIENT_BOT_MODE` — режим (`polling` по умолчанию).
- `CLIENT_SERVICE_HOST` — `0.0.0.0` по умолчанию.
- `CLIENT_SERVICE_PORT` — `8010` по умолчанию.
- `CLIENT_MASTERS_CHAT_ID` — chat_id мастер-чата (поддерживаются отрицательные `-100...`).
- `CLIENT_MASTER_USER_IDS` — список `user_id` мастеров (через запятую/пробел).
- `CLIENT_NOTIFY_MODE` — `dm_then_chat` по умолчанию (`dm_only`, `chat_only`, `chat_then_dm` поддержаны).
- `CLIENTS_REGISTRY_PATH` — optional путь к `clients.jsonl` (по умолчанию корень репозитория).

### reviews_bot_service
- `REVIEWS_TELEGRAM_BOT_TOKEN` (приоритет) или `TELEGRAM_BOT_TOKEN`.
- `REVIEWS_BOT_MODE` — режим (`polling` по умолчанию).
- `REVIEWS_SERVICE_HOST` — `0.0.0.0`.
- `REVIEWS_SERVICE_PORT` — `8020`.

При старте сервисы логируют `token source` и `mode` без вывода токена.

## Единая картотека `clients.jsonl`

Модель записи:
- `telegram_user_id`
- `telegram_username` (единый стандарт: **без @**)
- `full_name`
- `phones[]` (нормализация к `+7XXXXXXXXXX`)
- `car_numbers[]`
- `vin_codes[]`
- `email`, `vk_username`, `max_username`
- `created_at`, `updated_at` (ISO)
- `source_tags[]`

Правила обновления:
- ключ: `telegram_user_id`, fallback: `telegram_username`;
- массивы дополняются уникальными значениями (без перезаписи);
- `updated_at` всегда обновляется;
- `full_name` дополняется, если ранее был пустой;
- запись атомарная (`write-then-rename`) + lock-файл.

## Intake-логика client bot

Любое **private** сообщение клиента, которое не `/command`, считается обращением:
1. клиент upsert в `clients.jsonl`;
2. создаётся/обновляется тикет;
3. текст сохраняется в `comment`;
4. если телефона нет — статус `waiting_data`, клиенту запрос номера с примерами;
5. даже `waiting_data` тикет доставляется мастерам, чтобы обращение не терялось;
6. при валидном телефоне (`+7XXXXXXXXXX`) тикет переводится в `new`.

В тикетах фиксируются client-поля (`client_user_id`, `client_username`, `full_name`, `client_phone`).

## Master-chat и фильтр источников

- Для `CLIENT_MASTERS_CHAT_ID` обычные сообщения **не создают** тикеты.
- Обрабатываются только команды `/...` и callback-кнопки.
- Доступна команда `/tickets` (и `/new`) для списка `new + waiting_data`.
- Кнопки статусов: «В работу», «Запросить данные», «Обработана».

Доставка тикетов:
- по `CLIENT_NOTIFY_MODE`;
- ошибки конкретных мастеров 400/403 не останавливают рассылку остальным;
- при недоступности ЛС используется fallback в мастер-чат (если настроен).

## Pin flow

`pinned_message_id` хранится в storage как **int**.

Алгоритм:
1. есть `pinned_message_id` → пробуем `editMessageText/editReplyMarkup`;
2. `message is not modified` = успех, новый закреп не создаётся;
3. `message to edit not found` / `not enough rights` → fallback: создать новое сообщение и сохранить новый `pinned_message_id`;
4. если ID нет — создать закреп и сохранить ID.

## WebApp session/submit

### API
- `POST /api/webapp/session` → `session_token`, `ttl_seconds` или ошибка `invalid_init_data`.
- `POST /api/webapp/submit` принимает `session_token` или `initData`.
- различимые ошибки: `invalid_init_data`, `session_expired`, `phone_required`.

### Frontend
- перед submit пытается получить `/api/webapp/session`;
- submit отправляется через `/api/webapp/submit`;
- если session не получена, fallback на `initData`;
- телефон обязателен на фронте и сервере.

## Команды запуска

```bash
cd services/client_bot_service && python -m app.main
cd services/reviews_bot_service && python -m app.main
```

## Тесты

```bash
python -m unittest discover -s tests -p 'test_*.py'
```

Покрыто smoke-уровнем:
- webapp static routes;
- webapp session/submit;
- filter сообщений мастер-чата;
- pin parsing int/str;
- shared clients registry merge.
