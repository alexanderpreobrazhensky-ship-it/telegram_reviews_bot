# Client Bot (Telegram + WebApp)

Репозиторий содержит только `client-bot`.

## Запуск
```bash
python main.py
```

## Режимы
- `CLIENT_BOT_MODE=webhook` (по умолчанию)
- `CLIENT_BOT_MODE=polling` (fallback)

## Обязательные ENV
- `CLIENT_TELEGRAM_BOT_TOKEN`
- `BOT_PATH_SECRET`
- `PORT`
- `DOMAIN` или `WEBHOOK_URL`
- `CLIENT_WEBAPP_SESSION_SECRET`

Подробная инструкция: `README_AFTER_DEPLOY.md`.
