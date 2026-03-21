# MAX

## Active routes
- `/max/client_bot/webhook`
- `/max/master_bot/webhook`

## Current status
- MAX is embedded in the main Node project.
- Webhook validation requires `MAX_ENABLED`, token, and `MAX_WEBHOOK_SECRET`.
- Core bot behavior is implemented and covered by Node tests.
- Production readiness is partial: foundation is solid, but live-device and live-provider validation still matter.

## Important limitations
- No separate MAX BotHost project.
- No MAX integration bot.
- Identity trust is payload/runtime-based, not cryptographically verified in this repo.
