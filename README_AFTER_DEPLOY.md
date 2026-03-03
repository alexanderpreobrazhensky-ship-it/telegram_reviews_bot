# README_AFTER_DEPLOY (client-bot only)

## 1) Что в репозитории после очистки
- Оставлен только `client-bot`.
- Единственный production entrypoint: `main.py` в корне.
- Контейнер запускается только через Python (`Dockerfile` + `CMD ["python", "main.py"]`).
- WebApp-статика лежит только в `bots/client_bot/webapp/`.
- Файл картотеки клиентов: `./clients.jsonl` (по умолчанию).

## 2) BotHost checklist (быстрый старт)
1. Подключить репозиторий в BotHost.
2. Убедиться, что сборка идёт по `Dockerfile`.
3. Заполнить ENV (см. таблицу ниже).
4. Установить `CLIENT_BOT_MODE=webhook`.
5. Деплой.
6. Проверить:
   - `GET /health`
   - `GET /WEBAPP`
   - `GET /assets/webapp.bundle.js`
   - `GET /assets/webapp.bundle.css`

## 3) Режим запуска и webhook-first
По умолчанию бот стартует в `webhook` режиме:
- вычисляет webhook URL,
- вызывает `deleteWebhook(drop_pending_updates=True)`,
- затем `setWebhook(url=...)`,
- запускает Flask на `0.0.0.0:$PORT`.

Fallback:
- если `CLIENT_BOT_MODE=webhook`, но `WEBHOOK_URL`/`DOMAIN` невалидны или пусты, бот пишет warning и переходит в polling.

Важно:
- `BOT_PATH_SECRET` обязателен для webhook-режима (если пустой — startup error).

## 4) Как формируется webhook URL
Приоритет base URL:
1. `WEBHOOK_URL` (полный URL, например `https://bot_xxx.bothost.ru`)
2. `PUBLIC_BASE_URL`
3. `DOMAIN` (`bot_xxx.bothost.ru` -> `https://bot_xxx.bothost.ru`)

Путь всегда фиксированный:
- `/webhook/<BOT_PATH_SECRET>`

Итоговый URL:
- `<base>/webhook/<BOT_PATH_SECRET>`

## 5) WebApp маршруты
Статика:
- `GET /WEBAPP`
- `GET /WEBAPP/`
- `GET /assets/webapp.bundle.js`
- `GET /assets/webapp.bundle.css`
- `GET /app.js` (alias)
- `GET /app.css` (alias)

API:
- `POST /api/webapp/session`
- `POST /api/webapp/submit`
- `GET /api/webapp/lookup`
- `GET /WEBAPP/config.json`

## 6) Health endpoints
- `GET /health` -> `{"status":"ok","service":"client-bot","mode":"webhook|polling"}`
- `GET /service-health` -> alias с тем же payload.

## 7) Функциональность, которая осталась
- Intake private-сообщений клиента -> создание/обновление тикета.
- Если нет телефона -> `waiting_data` + запрос телефона.
- Если телефон есть -> `new`.
- Маршрутизация тикетов мастерам (DM/chat/комбинированные режимы).
- Мастер-чат команды `/tickets`, `/new`, `/waiting`, `/inprogress`, `/ticket <ID>`, `/queue`.
- Inline-статусы: `in_progress`, `waiting_data`, `processed`, `archived`, `postponed`.
- Очередь постов: `data/posts_queue.json` + worker внутри client-bot процесса.
- Pin-flow c `pinned_message_id` (int, edit-first стратегия, fallback на новый post).
- Единая картотека клиентов: `clients.jsonl` с lock + атомарной записью.

## 8) ENV таблица

### Required
- `CLIENT_TELEGRAM_BOT_TOKEN` — токен client-bot.
- `CLIENT_BOT_MODE` — `webhook` (default) или `polling`.
- `PORT` — порт Flask.
- `BOT_PATH_SECRET` — секретный path сегмент webhook.
- `CLIENT_WEBAPP_SESSION_SECRET` — подпись webapp session token.
- `CLIENT_WEBAPP_ENABLED` — `1/0`.

### Recommended
- `WEBHOOK_URL` — полный base URL (наивысший приоритет).
- `DOMAIN` — fallback для сборки base URL.
- `CLIENT_MASTERS_CHAT_ID` — chat мастеров.
- `CLIENT_MASTER_USER_IDS` — список master user id для DM.
- `CLIENT_NOTIFY_MODE` — `dm_then_chat|dm_only|chat_only|chat_then_dm`.
- `CLIENTS_REGISTRY_PATH` — путь к jsonl-картотеке (`./clients.jsonl` по умолчанию).

### Optional / Deprecated aliases
- `PUBLIC_BASE_URL` — fallback base URL.
- `WEBAPP_URL` — alias для `CLIENT_WEBAPP_URL`.
- `CLIENT_MASTER_IDS` — alias для `CLIENT_MASTER_USER_IDS`.
- `CLIENT_MASTER_CHAT_ID`, `CLIENT_CHAT_ID` — aliases для `CLIENT_MASTERS_CHAT_ID`.
- `ALLOW_TOKEN_FALLBACK` + `TELEGRAM_BOT_TOKEN|BOT_API_TOKEN|API_TOKEN|BOT_TOKEN|TOKEN`.

## 9) Чеклист "бот молчит"
1. `CLIENT_TELEGRAM_BOT_TOKEN` валиден.
2. `CLIENT_BOT_MODE=webhook`.
3. `BOT_PATH_SECRET` непустой.
4. Корректен `WEBHOOK_URL` или `DOMAIN`.
5. Приложение слушает `0.0.0.0:$PORT`.
6. `GET /health` отвечает 200.
7. В логах есть `deleteWebhook` и `setWebhook`.
