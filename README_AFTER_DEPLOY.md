# README_AFTER_DEPLOY

## BotHost: как запускать client-bot без Node-ошибок

### Рекомендованный вариант (Dockerfile)
1. Включите в BotHost опцию **"Использовать собственный Dockerfile"**.
2. Убедитесь, что главный процесс — `python main.py` (это уже зафиксировано в `Dockerfile`).
3. Проверьте в логах, что нет `Node.js v...`.

### Fallback, если Dockerfile недоступен в тарифе
1. В поле **Главный файл** укажите: `main.py`.
2. В поле команды запуска (если есть): `bash start.sh` (или напрямую `python main.py`).
3. Порт веб-приложения: `PORT` (BotHost системный), fallback `CLIENT_SERVICE_PORT`.

## Обязательные env для client-bot
- `CLIENT_TELEGRAM_BOT_TOKEN` (обязательно)
- `CLIENT_BOT_MODE=polling`
- `PORT` (или `CLIENT_SERVICE_PORT`)
- `DOMAIN` (например `bot_123456.bothost.ru`)
- `CLIENT_WEBAPP_ENABLED=1`
- `CLIENT_WEBAPP_SESSION_SECRET` (рекомендуется)

## Важные env (по фактическому использованию)
- `ALLOW_TOKEN_FALLBACK=1` — разрешает fallback токенов (`TELEGRAM_BOT_TOKEN`, `BOT_API_TOKEN`, `API_TOKEN`, `BOT_TOKEN`, `TOKEN`).
- `CLIENT_WEBAPP_URL` -> приоритетный публичный URL WebApp.
- `WEBAPP_URL` -> fallback URL.
- `WEBAPP_PATH` -> fallback путь (по умолчанию `/WEBAPP`).
- `CLIENT_MASTERS_CHAT_ID`, `CLIENT_MASTER_USER_IDS`, `CLIENT_NOTIFY_MODE` -> маршрутизация уведомлений мастерам.

## Контракт URL WebApp
Приоритет:
1. `CLIENT_WEBAPP_URL`
2. `WEBAPP_URL`
3. `https://{DOMAIN}{WEBAPP_PATH}`

Нормализация: удаляются лишние схемы/пробелы, URL приводится к `https://`.

## Контракт статики WebApp
Физические файлы (без entrypoint-имен):
- `/assets/webapp.bundle.js`
- `/assets/webapp.bundle.css`

Алиасы совместимости оставлены:
- `/app.js` -> bundle JS
- `/app.css` -> bundle CSS

## Health-check и smoke after deploy
Проверить в браузере/HTTP:
- `/health`
- `/WEBAPP`
- `/WEBAPP/config.json`
- `/assets/webapp.bundle.js`
- `/app.js`
- `/app.css`

Проверить в логах старта:
- `effective_bot=client`
- `mode=polling`
- `deleteWebhook ok`
- `polling started`
- `token_source=CLIENT_TELEGRAM_BOT_TOKEN` (или другой источник, без значения токена)

## Если бот не отвечает
1. Проверьте, что runtime Python, а не Node.
2. Проверьте `CLIENT_TELEGRAM_BOT_TOKEN`.
3. Проверьте `CLIENT_BOT_MODE=polling`.
4. Проверьте `deleteWebhook(drop_pending_updates=True)` в логах.
5. Проверьте доступность `/WEBAPP` и `/assets/webapp.bundle.js`.
