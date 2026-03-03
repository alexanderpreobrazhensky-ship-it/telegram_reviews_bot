# README_AFTER_DEPLOY (BotHost, webhook-first)

## BotHost: как заполнить поля
- Главный файл: `index.js`
- Ветка: `main`
- Порт в панели: `PORT` (или `8000`, если не задан)
- Webhook режим: через ENV `CLIENT_BOT_MODE=webhook`

## Что запускается
- `index.js` (Node bootstrap) запускает `python main.py` и пробрасывает `stdout/stderr`, env и сигналы `SIGTERM/SIGINT`.
- `main.py` запускает только `services.client_bot_service.app.main:main`.

## Webhook-first поведение
По умолчанию используется webhook (`CLIENT_BOT_MODE=webhook`).

Порядок:
1. Проверяется `BOT_PATH_SECRET` (обязателен в webhook-режиме).
2. Собирается base URL по приоритету:
   - `WEBHOOK_URL`
   - `PUBLIC_BASE_URL`
   - `DOMAIN` (нормализуется к `https://...`)
3. Формируется URL: `<base>/webhook/<BOT_PATH_SECRET>`.
4. Выполняется `deleteWebhook(drop_pending_updates=True)`.
5. Выполняется `setWebhook(url=...)`.
6. Flask стартует на `CLIENT_SERVICE_HOST` (default `0.0.0.0`) и `PORT`.

Fallback:
- Если режим webhook включён, но валидный base URL собрать не удалось — логируется warning и включается polling.
- Перед polling всегда вызывается `deleteWebhook(drop_pending_updates=True)`.

## WebApp и статика
Каноническая папка статики:
- `bots/client_bot/webapp/`

Критичные маршруты:
- `GET /WEBAPP`
- `GET /WEBAPP/`
- `GET /assets/webapp.bundle.js`
- `GET /assets/webapp.bundle.css`
- `GET /app.js` (alias)
- `GET /app.css` (alias)
- `GET /WEBAPP/config.json`

`index.html` ссылается только на:
- `/assets/webapp.bundle.js`
- `/assets/webapp.bundle.css`

Для статики выставляется `Cache-Control: no-cache, no-store, must-revalidate, max-age=0`.

## Проверки после деплоя
1. `GET /health` → 200
2. `GET /WEBAPP` → 200
3. `GET /assets/webapp.bundle.js` → 200
4. `GET /assets/webapp.bundle.css` → 200

## Обязательные ENV для webhook-first
- `CLIENT_TELEGRAM_BOT_TOKEN`
- `BOT_PATH_SECRET`
- `CLIENT_BOT_MODE` (`webhook` по умолчанию)
- `PORT` (или `CLIENT_SERVICE_PORT`, fallback `8000`)

## ENV (алфавитно): что читается и как маппится
- `API_TOKEN` → fallback токен (если пуст `CLIENT_TELEGRAM_BOT_TOKEN`)
- `BOT_API_TOKEN` → fallback токен
- `BOT_PATH_SECRET` → обязательный секрет пути `/webhook/<secret>` в webhook mode
- `BOT_TOKEN` → fallback токен
- `CLIENT_ADMIN_IDS` → список admin id (legacy-compatible парсинг)
- `CLIENT_BOT_MODE` → `webhook` (default) / `polling`
- `CLIENT_CHAT_ID` → alias для `CLIENT_MASTERS_CHAT_ID`
- `CLIENT_DATA_DIR` → data dir
- `CLIENT_MASTERS_CHAT_ID` → primary masters chat id
- `CLIENT_MASTER_CHAT_ID` → alias для `CLIENT_MASTERS_CHAT_ID`
- `CLIENT_MASTER_IDS` → alias для `CLIENT_MASTER_USER_IDS`
- `CLIENT_MASTER_USER_IDS` → primary список master user ids
- `CLIENT_SERVICE_HOST` → bind host (`0.0.0.0` default)
- `CLIENT_SERVICE_PORT` → fallback порт, если пуст `PORT`
- `CLIENT_TELEGRAM_BOT_TOKEN` → primary токен; если задан, используется только он
- `CLIENT_WEBAPP_ENABLED` / `WEBAPP_ENABLED` → включение WebApp роутов
- `CLIENT_WEBAPP_SESSION_SECRET` → secret подписи webapp session
- `CLIENT_WEBAPP_URL` / `WEBAPP_URL` → явный URL WebApp
- `DOMAIN` → fallback base URL (`https://<domain>`)
- `PORT` → основной порт
- `POSTGRESQL_URL` / `POSTGRES_URL` / `DATABASE_URL` → DB URL
- `PUBLIC_BASE_URL` → fallback base URL после `WEBHOOK_URL`
- `REPORT_CHAT_IDS` → список chat ids для отчётов
- `SUPERADMIN_ID` → superadmin id
- `TELEGRAM_BOT_TOKEN` → fallback токен
- `TOKEN` → fallback токен
- `WEBAPP_PATH` → путь WebApp (`/WEBAPP` default)
- `WEBHOOK_URL` → приоритетный base URL webhook

## Зависимости
Корневой `requirements.txt` содержит обязательные пакеты для client-bot (`Flask`, `requests`, `psycopg[binary]`, `Pillow`, `openpyxl`, `openai`, `httpx`) и `python-dotenv` для локального `.env`-режима.

## Команда запуска
- Для BotHost: выбрать главный файл `index.js`.
- Локально: `python main.py`.
