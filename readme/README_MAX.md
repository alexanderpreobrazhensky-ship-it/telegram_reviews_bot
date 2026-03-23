# MAX

## Active routes
- `/max/client_bot/webhook`
- `/max/master_bot/webhook`

## Master bot behavior
- Shares the same request state machine and menu callback logic as Telegram.
- MAX main menu uses the same stable callback ids.

## Clarification routing
- MAX-source requests send outbound clarification to MAX first.
- Fallback to Telegram is allowed only if a real `telegramId` exists.
- Email is never used as a fallback transport.

## Constraints
- No separate MAX BotHost project.
- No MAX integration bot.
