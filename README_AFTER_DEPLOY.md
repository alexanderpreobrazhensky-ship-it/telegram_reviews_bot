# README AFTER DEPLOY — Production Hardened

## 1. Архитектура
- `services/client_bot_service` — клиентский бот, WebApp API, тикеты, планировщик postponed.
- `services/reviews_bot_service` — сервис отзывов (legacy app wrapper), отдельный токен/порт.
- `shared/clients_registry.py` — единый реестр клиентов для обоих сервисов.
- Источник бизнес-логики client-бота: `bots/client_bot/main.py`.

## 2. Структура папок
- `services/client_bot_service/app` — entrypoint и конфиг сервиса клиента.
- `services/reviews_bot_service/app` — entrypoint и конфиг сервиса отзывов.
- `shared/clients_registry.py` — JSONL-реестр клиентов c lock/atomic write.
- `data/` — runtime storage (`tickets.jsonl`, `system.json` и пр.).
- `clients.jsonl` (корень репо) — общий реестр клиентов.

## 3. ENV таблицы (без fallback)
### client_bot_service (обязательно)
- `CLIENT_TELEGRAM_BOT_TOKEN` — **обязателен**, без него `RuntimeError` и сервис не стартует.
- `CLIENT_BOT_MODE` (default `polling`)
- `CLIENT_SERVICE_HOST` (default `0.0.0.0`)
- `CLIENT_SERVICE_PORT` (default `8010`)
- `CLIENT_ACTIVE_TICKET_TTL_HOURS` (default `12`)

### reviews_bot_service (обязательно)
- `REVIEWS_TELEGRAM_BOT_TOKEN` — **обязателен**, без него `RuntimeError` и сервис не стартует.
- `REVIEWS_BOT_MODE` (default `polling`)
- `REVIEWS_SERVICE_HOST` (default `0.0.0.0`)
- `REVIEWS_SERVICE_PORT` (default `8020`)

## 4. Clients registry logic
- Общий путь: `./clients.jsonl` в корне репозитория.
- Lock-файл: `clients.lock` рядом с реестром.
- Lock timeout: `CLIENTS_REGISTRY_LOCK_TIMEOUT_SECONDS` (default 5s).
- Атомарная запись: temp file + `os.replace`.
- Ключи поиска: `telegram_user_id` (primary), `telegram_username` (fallback).
- При update:
  - массивы (`phones`, `car_numbers`, `vin_codes`, `source_tags`) мерджатся уникально;
  - `created_at` сохраняется;
  - `updated_at` обновляется всегда.
- Если файла нет — создаётся автоматически.

## 5. Ticket lifecycle + TTL
- Активный тикет переиспользуется при статусах: `new`, `waiting_data`, `in_progress`/`in_work`.
- Активность определяется по `updated_at` (fallback `created_at`) + `CLIENT_ACTIVE_TICKET_TTL_HOURS`.
- Если TTL истёк — создаётся новый тикет.

## 6. Postponed scheduler
- Поддерживается статус `postponed` и поле `postponed_until` (ISO datetime).
- В polling-цикле проверка каждые 60 секунд.
- Если `now >= postponed_until`:
  - статус меняется на `new`;
  - `postponed_until` очищается;
  - тикет повторно отправляется мастерам.
- Логика безопасна после рестарта: данные читаются из storage.

## 7. Master-chat filter
- Для `CLIENT_MASTERS_CHAT_ID` сообщения без `/command` не создают тикет.
- Добавлено логирование: `master_chat_message_ignored`.
- Reply-обработка в мастере допускается только при наличии метки `TICKET_ID:` в replied message.
- Поддерживаются chat_id форматы включая `-100...`.

## 8. Notify modes
- Используются существующие режимы доставки уведомлений мастерам (`dm/chat`) без удаления прежней логики.

## 9. Pin flow алгоритм
- `pinned_message_id` хранится как `int` в `data/system.json` (core setting).
- На старте/обновлении выполняются:
  1) `editMessageText`
  2) `editMessageReplyMarkup`
- `message is not modified` считается успешным сценарием.
- `message to edit not found` => fallback на создание нового pinned message.
- Для pin-id используется безопасный `parse_int_maybe`; не завязано на `.isdigit()` в критичном path.

## 10. WebApp session/submit
- `POST /api/webapp/session`:
  - возвращает `session_token`, `ttl_seconds`;
  - явные причины отказа (`invalid_init_data`, `reason`).
- `POST /api/webapp/submit`:
  - принимает `session_token`;
  - fallback на `initData`;
  - ошибки: `invalid_init_data`, `session_expired`, `phone_required`.
- При отсутствии телефона: `400` + JSON error.
- Логи содержат статус submit, без полного дампа initData.

## 11. Health endpoint
У обоих сервисов доступны:
- `GET /health`
- `GET /service-health` (legacy совместимость)

Формат:
```json
{
  "status": "ok",
  "service": "client_bot_service",
  "mode": "polling"
}
```

## 12. Точные команды запуска
### Client
```bash
export CLIENT_TELEGRAM_BOT_TOKEN="..."
python -m services.client_bot_service.app.main
```

### Reviews
```bash
export REVIEWS_TELEGRAM_BOT_TOKEN="..."
python -m services.reviews_bot_service.app.main
```

## 13. Точные команды тестов
### Root smoke
```bash
python -m unittest discover -s tests
```

### Client
```bash
cd services/client_bot_service
python -m unittest discover
```

### Reviews
```bash
cd services/reviews_bot_service
python -m unittest discover
```

## 14. Ограничения Telegram
- Возможны 400-ошибки на edit/pin при недоступном сообщении/правах.
- При конфликте polling/webhook Telegram может вернуть 409.
- Ограничения parse mode/markup могут требовать fallback без клавиатуры.

## 15. Known edge cases
- Неизвестный plain-text в master chat игнорируется и логируется.
- Исторические тикеты без корректной даты могут трактоваться как активные до первого нормального update.
- При неверном initData `submit` возвращает `invalid_init_data`.
- При просроченном session token/initData `submit` возвращает `session_expired`.
