# README_AFTER_DEPLOY

## 1) BotHost production запуск (client-bot)

### Рекомендуемый вариант (обязательно): Dockerfile
- В корне добавлен `Dockerfile` с **python-only** запуском: `CMD ["python", "main.py"]`.
- В Dockerfile нет установки Node.js и нет node-команд.
- На BotHost включите опцию **"Использовать собственный Dockerfile"** (если доступна).

### Entry point
- Корневой entrypoint: `main.py`.
- Команда запуска: `python main.py`.
- `main.py` вызывает только `services.client_bot_service.app.main:main`.

## 2) ENV переменные client-bot (алфавитно)

- `ALLOW_TOKEN_FALLBACK` — `1` разрешает fallback токена на `TELEGRAM_BOT_TOKEN/BOT_API_TOKEN/API_TOKEN/BOT_TOKEN/TOKEN`. По умолчанию fallback выключен.
- `API_TOKEN` — fallback токен (используется только при `ALLOW_TOKEN_FALLBACK=1`).
- `BOT_TOKEN` — дополнительный fallback токен (используется только при `ALLOW_TOKEN_FALLBACK=1`).
- `BOT_API_TOKEN` — fallback токен (используется только при `ALLOW_TOKEN_FALLBACK=1`).
- `BOT_PATH_SECRET` — fallback secret для WebApp session token.
- `CLIENT_BOT_MODE` — режим бота (`polling` по умолчанию, `webhook` оставлен на будущее).
- `CLIENT_DATA_DIR` — путь к данным сервиса (default `data`).
- `CLIENT_SERVICE_HOST` — host Flask (default `0.0.0.0`).
- `CLIENT_SERVICE_PORT` — fallback порт, если нет `PORT`.
- `CLIENT_TELEGRAM_BOT_TOKEN` — основной токен client-bot (обязательный в нормальном режиме).
- `CLIENT_WEBAPP_ENABLED` — включение WebApp (default включено).
- `CLIENT_WEBAPP_INITDATA_MAX_AGE_SECONDS` — TTL initData для сессий WebApp.
- `CLIENT_WEBAPP_SESSION_SECRET` — секрет подписи webapp session.
- `CLIENT_WEBAPP_URL` — приоритетный публичный URL WebApp.
- `CLIENT_NOTIFY_MODE` — режим доставки в DM/мастер-чат.
- `CLIENT_MASTER_USER_IDS` — id мастеров для DM.
- `CLIENT_MASTERS_CHAT_ID` — id мастер-чата.
- `DATABASE_URL` — Postgres DSN, включает DB режим.
- `DOMAIN` — хост BotHost (например `bot_12345.bothost.ru`) для fallback сборки WebApp URL.
- `LIRA_ADDRESS` — адрес в WebApp/боте.
- `LIRA_PHONE` — телефон в WebApp/боте.
- `PORT` — приоритетный порт (важно для BotHost).
- `POSTGRESQL_URL` — fallback DSN.
- `POSTGRES_URL` — fallback DSN.
- `TELEGRAM_BOT_TOKEN` — fallback токен (только при `ALLOW_TOKEN_FALLBACK=1`).
- `TOKEN` — дополнительный fallback токен (только при `ALLOW_TOKEN_FALLBACK=1`).
- `TIMEZONE` — таймзона.
- `WEBAPP_ENABLED` — fallback флаг webapp.
- `WEBAPP_PATH` — путь webapp (default `/WEBAPP`).
- `WEBAPP_URL` — fallback URL webapp.

## 3) Контракт токенов

- По умолчанию читается **только** `CLIENT_TELEGRAM_BOT_TOKEN`.
- Fallback токены (`TELEGRAM_BOT_TOKEN`, `BOT_API_TOKEN`, `API_TOKEN`, `BOT_TOKEN`, `TOKEN`) включаются **только** при `ALLOW_TOKEN_FALLBACK=1`.
- В логах пишется `effective_bot=client` и `token_source=...` (без секрета); root `main.py` также логирует старт сервиса до инициализации Flask.

## 4) Контракт URL WebApp

Приоритет URL:
1. `CLIENT_WEBAPP_URL`
2. `WEBAPP_URL`
3. `https://{DOMAIN}{WEBAPP_PATH}`

Нормализация:
- очищается схема из `DOMAIN`, если случайно передана (`https://...`),
- убираются двойные схемы (`https://HTTPS://...`, `https://http://...`),
- финальный URL приводится к `https://`.

## 5) WebApp маршруты

Поддерживаются и новый путь, и обратная совместимость:
- `GET /WEBAPP` → 200 (index)
- `GET /webapp.js` → 200 (новый файл)
- `GET /app.js` → 200 (алиас)
- `GET /webapp.css` → 200 (новый файл)
- `GET /app.css` → 200 (алиас)
- `GET /WEBAPP/config.json` → 200

## 6) Polling/Webhook

- В `polling` режиме на старте вызывается `deleteWebhook(drop_pending_updates=True)`.
- После этого запускается polling цикл.
- В логах есть: mode, polling started, deleteWebhook, token_source.

## 7) Storage режим

- Если задан `DATABASE_URL`/`POSTGRES_URL`/`POSTGRESQL_URL` и драйвер доступен → `storage_mode=db`.
- Иначе → `storage_mode=files`:
  - `clients.jsonl` (корень репо)
  - `data/tickets.jsonl`
  - `data/system.json`
  - `data/posts_queue.json` (очередь постов client-bot)

## 8) Пример ENV для BotHost (без секретов)

```env
CLIENT_TELEGRAM_BOT_TOKEN=123456:REDACTED
CLIENT_BOT_MODE=polling
PORT=8000
DOMAIN=bot_123456.bothost.ru
CLIENT_WEBAPP_URL=https://bot_123456.bothost.ru/WEBAPP
CLIENT_WEBAPP_ENABLED=1
CLIENT_WEBAPP_SESSION_SECRET=change-me
CLIENT_NOTIFY_MODE=dm_then_chat
CLIENT_MASTER_USER_IDS=111111111,222222222
CLIENT_MASTERS_CHAT_ID=-1001234567890
DATABASE_URL=postgresql://user:pass@host:5432/dbname
ALLOW_TOKEN_FALLBACK=0
```

## 9) Чеклист "если бот не отвечает"

1. Проверить, что BotHost стартует через Dockerfile/`python main.py`, а не Node.
2. Проверить `CLIENT_TELEGRAM_BOT_TOKEN`.
3. Проверить логи: `effective_bot=client`, `mode=polling`, `polling started`, `deleteWebhook`.
4. Проверить, что не включён случайный webhook и что `deleteWebhook` успешен.
5. Проверить `PORT`/`CLIENT_SERVICE_PORT`.
6. Проверить `CLIENT_MASTER_USER_IDS`/`CLIENT_MASTERS_CHAT_ID` (для уведомлений мастерам).
7. Проверить доступность WebApp:
   - `/WEBAPP`
   - `/webapp.js` и `/app.js`
   - `/WEBAPP/config.json`
