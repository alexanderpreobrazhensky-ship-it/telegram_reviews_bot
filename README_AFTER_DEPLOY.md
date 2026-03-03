# README_AFTER_DEPLOY

## BotHost-first (только Python)
- Запуск только через `python main.py`.
- Контракт контейнера: `Dockerfile` использует только Python-зависимости и `CMD ["python", "main.py"]`.
- В корне нет Node entrypoint (`package.json`, `server.js`, `index.js`, `app.js`).

## Режимы запуска client-bot
- `CLIENT_BOT_MODE=webhook` — основной режим (по умолчанию).
- `CLIENT_BOT_MODE=polling` — только аварийный fallback/локальная отладка.

## Обязательные ENV для webhook
- `CLIENT_TELEGRAM_BOT_TOKEN`
- `BOT_PATH_SECRET` (формирует путь `/webhook/<BOT_PATH_SECRET>`)
- `PUBLIC_BASE_URL` (или `DOMAIN` как fallback)
- `PORT`

## ENV URL-контракт
- Base URL: `PUBLIC_BASE_URL` → fallback `DOMAIN`.
- Принудительно используется `https://`.
- Webhook URL: `https://<host>/webhook/<BOT_PATH_SECRET>`.
- WebApp URL: `CLIENT_WEBAPP_URL` → `WEBAPP_URL` → `PUBLIC_BASE_URL + WEBAPP_PATH`.
- `WEBAPP_PATH` по умолчанию `/WEBAPP`.

## Startup-последовательность в webhook
1. `deleteWebhook(drop_pending_updates=True)`.
2. Расчёт публичного URL.
3. `setWebhook(url=..., secret_token=BOT_PATH_SECRET)`.
4. Старт HTTP-сервера `0.0.0.0:$PORT`.

## Smoke после деплоя
Проверить:
- `/health`
- `POST /webhook/<BOT_PATH_SECRET>`
- `/WEBAPP`
- `/assets/webapp.bundle.js`
- `/assets/webapp.bundle.css`
- `/app.js`
- `/app.css`
