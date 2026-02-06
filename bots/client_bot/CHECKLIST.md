## Checklist: деплой client_bot в одном Railway service

### Подготовка переменных окружения

1. Установить `CLIENT_TELEGRAM_BOT_TOKEN` = токен **клиентского** бота (BotFather).
2. Убедиться, что `TELEGRAM_BOT_TOKEN` остаётся токеном `reviews_bot` (не использовать в client_bot).
3. Задать `MASTER_USERNAMES` (обязательно) и при необходимости `TIMEZONE`, `REMINDER_MINUTES`.
4. При использовании AI задать `CLIENT_*` переменные (см. README).

### Деплой

1. Выполнить redeploy Railway service.
2. В Deploy Logs проверить:
   - строка `client_bot token source: CLIENT_TELEGRAM_BOT_TOKEN|TELEGRAM_BOT_TOKEN_CLIENT`;
   - строка `client_bot deleteWebhook ok` (или warning о том, что webhook уже удалён);
   - отсутствие `409 Conflict` в polling.

### Проверка работоспособности

1. В Telegram отправить `/start` в **client_bot** — бот должен ответить.
2. Убедиться, что `reviews_bot` продолжает работать как раньше (webhook не сломан).

### Где смотреть логи

- Railway → Deploy Logs (service с `client_bot`).
