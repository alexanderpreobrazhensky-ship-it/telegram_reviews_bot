# client_bot

`client_bot` — клиентский Telegram-бот автосервиса «Автоцентр Лира».

## Production contract (единый)
- Production branch: `main`.
- Production runtime: **Python**.
- Production deploy path: **Dockerfile-first**.
- Entrypoint: корневой `main.py` (цепочка `main.py` → `services/client_bot_service/app/main.py` → `bots/client_bot/main.py`).
- Режим по умолчанию: `webhook`.
- Node bootstrap не используется в production; корень репозитория Python-only для платформы.

## Минимальный env для первого запуска
### Webhook-first (рекомендуется)
- `CLIENT_TELEGRAM_BOT_TOKEN` (или alias токена)
- `BOT_PATH_SECRET`
- один из: `WEBHOOK_URL` / `PUBLIC_BASE_URL` / `DOMAIN`

### Polling (fallback/forced)
- `CLIENT_TELEGRAM_BOT_TOKEN`
- `CLIENT_BOT_MODE=polling`

## Поддерживаемые alias-группы
- Token: `CLIENT_TELEGRAM_BOT_TOKEN`, `TELEGRAM_BOT_TOKEN`, `BOT_API_TOKEN`, `API_TOKEN`, `BOT_TOKEN`, `TOKEN`
- Mode: `CLIENT_BOT_MODE`, `CLIENT_RUN_MODE`, `RUN_MODE`
- Port: `PORT`, `CLIENT_SERVICE_PORT`
- Base URL: `WEBHOOK_URL`, `PUBLIC_BASE_URL`, `DOMAIN`
- WebApp URL/path: `CLIENT_WEBAPP_URL`, `WEBAPP_URL`, `WEBAPP_PATH`
- WebApp enabled: `CLIENT_WEBAPP_ENABLED`, `WEBAPP_ENABLED`
- Masters: `CLIENT_MASTERS_CHAT_ID`, `CLIENT_CHAT_ID`, `CLIENT_MASTER_CHAT_ID`, `CLIENT_MASTER_USER_IDS`, `CLIENT_MASTER_IDS`

## Проверки после деплоя
- `GET /health`
- `GET /service-health`
- `GET /WEBAPP`
- `getWebhookInfo` через Telegram Bot API

## Важно
- BotFather Main App/Menu Button влияет только на открытие WebApp.
- BotFather не определяет runtime и не заменяет Dockerfile + `main.py` контракт.
