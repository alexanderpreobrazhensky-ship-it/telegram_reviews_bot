# AUDIT_AFTER_CODEX (client-bot only, detailed)

## Итог
Репозиторий переведён в single-service режим: только `client-bot`.

## 1) Что удалено полностью
- `services/reviews_bot_service/` (весь сервис отзывов).
- `bots/reviews_bot/`.
- `review_fetch.py`.
- `review.html`.
- review-oriented тесты (`tests/test_bot.py`) и smoke-проверки, импортировавшие reviews service.

## 2) Что осталось
- Корневой entrypoint: `main.py`.
- Service layer: `services/client_bot_service/app/*`.
- Bot logic: `bots/client_bot/main.py`.
- Shared clients registry: `shared/clients_registry.py`.
- WebApp assets:
  - `bots/client_bot/webapp/index.html`
  - `bots/client_bot/webapp/assets/webapp.bundle.js`
  - `bots/client_bot/webapp/assets/webapp.bundle.css`

## 3) Entry point и runtime-контракт
- Root `main.py` запускает только `services.client_bot_service.app.main.main`.
- В startup-логе используется явный маркер `client-bot starting ...`.
- `Dockerfile` строго python-only:
  - `FROM python:3.11-slim`
  - `CMD ["python", "main.py"]`

## 4) Webhook-first логика
Порядок старта в `services/client_bot_service/app/main.py`:
1. Чтение ENV в `ClientBotConfig.from_env()`.
2. Инициализация telegram клиента.
3. Если mode=`webhook`:
   - при валидном webhook URL -> `deleteWebhook(drop_pending_updates=True)` -> `setWebhook(url=...)`.
   - при невалидном/пустом base URL -> warning + fallback в polling.
4. Если mode=`polling`: запуск polling + `deleteWebhook(drop_pending_updates=True)`.

Жёсткое условие:
- В webhook mode `BOT_PATH_SECRET` обязателен, иначе runtime error.

## 5) Health
- `/health` и `/service-health` в service app.
- Payload: `status=ok`, `service=client-bot`, `mode=webhook|polling`.

## 6) WebApp/Static контракты
Поддерживаются маршруты:
- `/WEBAPP`, `/WEBAPP/`
- `/assets/webapp.bundle.js`
- `/assets/webapp.bundle.css`
- `/app.js`, `/app.css` (алиасы)
- `/WEBAPP/config.json`
- `/api/webapp/session`
- `/api/webapp/submit`
- `/api/webapp/lookup`

## 7) ENV аудит (алфавитно)
- `ALLOW_TOKEN_FALLBACK` — включить chain fallback токенов.
- `API_TOKEN` — fallback token alias.
- `BOT_API_TOKEN` — fallback token alias.
- `BOT_PATH_SECRET` — required в webhook mode.
- `BOT_TOKEN` — fallback token alias.
- `CLIENT_BOT_MODE` — `webhook` default, `polling` fallback.
- `CLIENT_CHAT_ID` — deprecated alias для `CLIENT_MASTERS_CHAT_ID`.
- `CLIENT_DATA_DIR` — data-dir override.
- `CLIENT_MASTERS_CHAT_ID` — chat id мастеров.
- `CLIENT_MASTER_CHAT_ID` — deprecated alias.
- `CLIENT_MASTER_IDS` — deprecated alias.
- `CLIENT_MASTER_USER_IDS` — список мастеров для DM.
- `CLIENT_SERVICE_HOST` — host bind (`0.0.0.0`).
- `CLIENT_SERVICE_PORT` — fallback порта если `PORT` пустой.
- `CLIENT_TELEGRAM_BOT_TOKEN` — основной обязательный токен.
- `CLIENT_WEBAPP_ENABLED` — включение webapp роутов.
- `CLIENT_WEBAPP_SESSION_SECRET` — секрет подписи webapp session.
- `CLIENT_WEBAPP_URL` — override внешнего URL webapp.
- `CLIENTS_REGISTRY_PATH` — путь к `clients.jsonl`.
- `DATABASE_URL` — postgres URL.
- `DOMAIN` — fallback base URL.
- `PORT` — основной HTTP порт.
- `POSTGRESQL_URL` — database alias.
- `POSTGRES_URL` — database alias.
- `PUBLIC_BASE_URL` — fallback base URL после `WEBHOOK_URL`.
- `RUN_MODE` — legacy alias режима.
- `TELEGRAM_BOT_TOKEN` — fallback alias токена.
- `TOKEN` — fallback alias токена.
- `WEBAPP_PATH` — путь webapp (`/WEBAPP` default).
- `WEBAPP_URL` — alias для webapp URL.
- `WEBHOOK_URL` — приоритетный base URL webhook.

## 8) Почему бот может "молчать" (чеклист)
1. Неверный/пустой `CLIENT_TELEGRAM_BOT_TOKEN`.
2. В webhook mode пустой `BOT_PATH_SECRET`.
3. Не задан `WEBHOOK_URL` и пустой `DOMAIN` -> fallback polling там, где polling недоступен.
4. Неверный `PORT` или bind не на `0.0.0.0`.
5. В BotHost не применились новые ENV после redeploy.
6. `CLIENT_WEBAPP_ENABLED=0`, из-за чего WebApp маршруты возвращают 404.

## 9) Как проверить webhook через Telegram getWebhookInfo
1. Взять токен бота.
2. Выполнить HTTP GET к API Telegram:
   - `https://api.telegram.org/bot<token>/getWebhookInfo`
3. Проверить поля:
   - `url` совпадает с `https://<base>/webhook/<BOT_PATH_SECRET>`.
   - `pending_update_count` не растёт бесконечно.
   - нет `last_error_message`/`last_error_date`.
4. Если URL пустой — webhook не установлен, проверить startup-логи и ENV.
