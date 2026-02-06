## Назначение

`client_bot` работает **только через polling (getUpdates)** и использует **отдельный Telegram-токен**
для клиентского бота. `client_bot` **никогда не вызывает setWebhook**. При старте и при 409 бот
пытается удалить webhook через `deleteWebhook` и продолжает работу в polling-режиме.

## Переменные окружения (client_bot)

Для безопасного запуска в одном Railway service с другим ботом используйте префикс `CLIENT_`.
Эти переменные не конфликтуют с настройками `reviews_bot`.

### Telegram

`client_bot` читает токен **только** из:

1. `CLIENT_TELEGRAM_BOT_TOKEN` (приоритет)
2. `TELEGRAM_BOT_TOKEN_CLIENT` (fallback)

`TELEGRAM_BOT_TOKEN` (токен `reviews_bot`) **никогда не используется**.

### AI (DeepSeek)

Приоритет чтения: `CLIENT_*` → старые имена (fallback).

- `CLIENT_DEEPSEEK_API_KEY` (fallback: `DEEPSEEK_API_KEY`)
- `CLIENT_DEEPSEEK_BASE_URL` (fallback: `DEEPSEEK_BASE_URL`)
- `CLIENT_DEEPSEEK_MODEL` (fallback: `DEEPSEEK_MODEL`)
- `CLIENT_AI_TIMEOUT_SECONDS` (fallback: `AI_TIMEOUT_SECONDS`, по умолчанию `10`)
- `CLIENT_FORCE_FALLBACK` (fallback: `FORCE_FALLBACK`, `1` — только fallback)

### Прочее

- `MASTER_USERNAMES` — список Telegram-юзернеймов мастеров через запятую (обязателен).
- `REMINDER_MINUTES` — период напоминаний мастеру (по умолчанию `30`).
- `TIMEZONE` — часовой пояс (по умолчанию `Europe/Moscow`).

## Диагностика 409 Conflict

Если видите ошибку `409 Conflict`, значит webhook включён на **этом** токене.
`client_bot` сам попробует `deleteWebhook` и продолжит polling.
