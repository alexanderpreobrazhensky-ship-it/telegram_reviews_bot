## Переменные окружения (client_bot)

Для безопасного запуска в одном Railway service с другим ботом используйте префикс `CLIENT_`.
Эти переменные не конфликтуют с настройками `reviews_bot`.

### AI (DeepSeek)

Приоритет чтения: `CLIENT_*` → старые имена (fallback).

- `CLIENT_DEEPSEEK_API_KEY` (fallback: `DEEPSEEK_API_KEY`)
- `CLIENT_DEEPSEEK_BASE_URL` (fallback: `DEEPSEEK_BASE_URL`)
- `CLIENT_DEEPSEEK_MODEL` (fallback: `DEEPSEEK_MODEL`)
- `CLIENT_AI_TIMEOUT_SECONDS` (fallback: `AI_TIMEOUT_SECONDS`, по умолчанию `10`)
- `CLIENT_FORCE_FALLBACK` (fallback: `FORCE_FALLBACK`, `1` — только fallback)
