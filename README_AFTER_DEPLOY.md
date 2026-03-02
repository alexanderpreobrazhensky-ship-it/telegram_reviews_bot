# README_AFTER_DEPLOY

## BotHost-first запуск
- Основной entrypoint: `python main.py`.
- Альтернативный запуск через `start.sh` (выполняет только `exec python main.py`).
- Docker-контракт: `Dockerfile` запускает Python-приложение через `CMD ["python", "main.py"]`.

## Обязательные env
- `CLIENT_TELEGRAM_BOT_TOKEN` — токен client-bot.
- `CLIENT_BOT_MODE` — `polling` (рекомендуется для BotHost) или `webhook`.
- `PORT` — порт HTTP-сервиса.

## Опциональные env
- `DOMAIN` — внешний домен для построения URL.
- `WEBHOOK_URL` — явный URL webhook (если используется webhook-режим).
- `CLIENT_WEBAPP_URL` / `WEBAPP_URL` — публичный URL Mini App.
- `WEBAPP_PATH` — путь WebApp (по умолчанию `/WEBAPP`).

## Проверка после деплоя
Проверить HTTP-эндпоинты:
- `/health`
- `/WEBAPP`
- `/WEBAPP/config.json`
- `/assets/webapp.bundle.js`
- `/assets/webapp.bundle.css`
- `/app.js`
- `/app.css`

## Polling/Webhook правила
- `CLIENT_BOT_MODE=polling`: бот удаляет webhook и запускает polling.
- `CLIENT_BOT_MODE=webhook`: webhook используется только при валидном внешнем URL.
- При невалидном URL в webhook-режиме включается безопасный fallback на polling.
