# README_AFTER_DEPLOY (BotHost, webhook-first)

## BotHost: как заполнить поля
- **Главный файл:** `index.js`
- **Ветка:** `main`
- **Порт в панели:** `PORT` (если пусто — fallback `8000`)

## Что запускается на самом деле
1. BotHost стартует `index.js` (Node bootstrap).
2. `index.js` делает `spawn("python", ["main.py"])`, наследует ENV/stdio и пробрасывает SIGTERM/SIGINT.
3. Root `main.py` логирует `client-bot starting (root main.py)` и вызывает только `services.client_bot_service.app.main:main`.

Это гарантирует Python-рантайм даже при Node-автодетекте платформы.

## ENV для первого успешного webhook-first запуска
**Обязательные:**
- `CLIENT_TELEGRAM_BOT_TOKEN`
- `BOT_PATH_SECRET`

**Рекомендуемые:**
- `WEBHOOK_URL` (или `PUBLIC_BASE_URL`, или `DOMAIN`)
- `PORT`

**Опциональные:**
- `CLIENT_BOT_MODE` (default `webhook`; можно поставить `polling`)
- `CLIENT_SERVICE_HOST` (default `0.0.0.0`)

## Webhook-first поведение
По умолчанию `CLIENT_BOT_MODE=webhook`.

Приоритет base URL:
1. `WEBHOOK_URL`
2. `PUBLIC_BASE_URL`
3. `DOMAIN` (нормализуется в `https://<domain>`)

Итоговый webhook URL: `<base>/webhook/<BOT_PATH_SECRET>`.

Порядок старта:
1. Проверка `BOT_PATH_SECRET` (если нет — быстрый `RuntimeError`).
2. `deleteWebhook(drop_pending_updates=True)`.
3. `setWebhook(url=...)`.
4. HTTP-сервер на `0.0.0.0:$PORT`.

Fallback:
- Если выбран webhook, но base URL не собирается — warning и переход в polling.
- Перед polling всегда вызывается `deleteWebhook(drop_pending_updates=True)`.

## Проверка после деплоя
- `GET /health` → `200`
- `GET /service-health` → `200`
- `GET /WEBAPP` → `200`
- `GET /assets/webapp.bundle.js` → `200`
- `GET /assets/webapp.bundle.css` → `200`
- `GET /WEBAPP/config.json` → `200`
- `GET /app.js` и `GET /app.css` (алиасы) → `200`

## Проверка webhook в Telegram
Откройте:
- `https://api.telegram.org/bot<TOKEN>/getWebhookInfo`

Проверьте, что:
- `url` совпадает с `https://<bothost-domain>/webhook/<BOT_PATH_SECRET>`
- `last_error_message` пустой
- `pending_update_count` не растёт

## BotFather: смена Main App URL (важно)
Если в BotFather всё ещё предыдущий хостинг URL, WebApp будет открываться не там.

Нужно обновить:
- **Main App URL**
- **Menu Button URL**

На адрес BotHost:
- `https://<bothost-domain>/WEBAPP`

## Если в логах снова видно `Node.js v...` / SyntaxError по `main.py`
Чеклист:
1. В BotHost «Главный файл» строго `index.js`.
2. В корне репозитория нет `package.json`, `app.js`, `server.js`, `main.js`.
3. В логах есть строка Python-старта: `client-bot starting (root main.py)`.
4. В логах есть диагностика: `effective_runtime=node_bootstrap python_entrypoint=main.py ...`.

## Команды запуска
- BotHost: запускает `index.js`
- Локально: `python main.py`
