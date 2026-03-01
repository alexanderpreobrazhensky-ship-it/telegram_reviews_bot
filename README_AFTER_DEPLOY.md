# README AFTER DEPLOY

## Services
- `services/client_bot_service` — production entrypoint для client bot + WebApp API.
- `services/reviews_bot_service` — production entrypoint для reviews bot (обёртка legacy `main.py`).
- Общая логика client bot: `bots/client_bot/main.py`.
- Общий реестр клиентов: `shared/clients_registry.py` -> `./clients.jsonl`.

## Run commands
### From repo root
- Client bot: `python -m services.client_bot_service.app.main`
- Reviews bot: `python -m services.reviews_bot_service.app.main`

### From service folders
- Client bot:
  - `cd services/client_bot_service`
  - `python -m app.main`
- Reviews bot:
  - `cd services/reviews_bot_service`
  - `python -m app.main`

## Required ENV
### Client bot
- `CLIENT_TELEGRAM_BOT_TOKEN` (required)
- `CLIENT_SERVICE_PORT` (default `8010`)
- `CLIENT_SERVICE_HOST` (default `0.0.0.0`)
- `CLIENT_BOT_MODE` (default `polling`)

### Reviews bot
- `REVIEWS_TELEGRAM_BOT_TOKEN` (required)
- `REVIEWS_SERVICE_PORT` (default `8020`)
- `REVIEWS_SERVICE_HOST` (default `0.0.0.0`)
- `REVIEWS_BOT_MODE` (default `polling`)

## Ticket flow
- Основные статусы: `new -> in_progress -> waiting_data -> processed -> archived`.
- Дополнительно поддерживается `postponed` + `postponed_until`.
- `CLIENT_ACTIVE_TICKET_TTL_HOURS` (default `12`) контролирует переиспользование активного тикета.
- Проверка postponed выполняется раз в 60 секунд в polling loop.

## Master delivery
- `CLIENT_NOTIFY_MODE`:
  - `dm_then_chat` (default)
  - `dm_only`
  - `chat_only`
  - `chat_then_dm`
- Ошибки 400/403 доставки не ломают сохранение тикета.

## WebApp API
- `POST /api/webapp/session` -> `{ok:true,session_token,ttl_seconds}` или `{ok:false,error:"invalid_init_data",reason}`.
- `POST /api/webapp/submit`:
  - поддерживает `session_token` (приоритет)
  - fallback на `initData`
  - без телефона: `400 {ok:false,error:"phone_required"}`

## Shared clients registry
- Файл: `./clients.jsonl` (по умолчанию), override: `CLIENTS_REGISTRY_PATH`.
- Lock: `clients.lock`, timeout: `CLIENTS_REGISTRY_LOCK_TIMEOUT_SECONDS` (default `5`).
- Atomic write: temp + `os.replace`.

## Tests
- Локально: `python -m unittest discover -s tests -p 'test_*.py'`
- CI: `.github/workflows/tests.yml` запускает unit tests для обоих сервисов.
