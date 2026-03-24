# MAX

## Active webhook routes
- `POST /max/client_bot/webhook`
- `POST /max/master_bot/webhook`

## Runtime model
MAX работает внутри того же Node runtime, что и Telegram/WebApp.
Отдельный MAX BotHost/проект не используется.

## Master bot behavior in MAX
- Та же status/substatus модель, что и в Telegram.
- То же callback-меню и flow карточек заявок.
- AI/diagnostics/admin поведение единообразно с Telegram (в рамках ролей).

## Clarification routing
Для заявок из MAX первичный outbound канал — MAX;
fallback в Telegram допускается только при подтверждённом `telegramId`.
Email не используется как outbound fallback.

## MAX readiness checks
Используются `/health/max` и master diagnostics:
- enabled/disabled state
- token/secret readiness
- webhook route availability
