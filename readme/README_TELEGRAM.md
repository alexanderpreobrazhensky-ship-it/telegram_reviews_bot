# Telegram

## Active routes
- `/telegram/client_bot/webhook`
- `/telegram/master_bot/webhook`
- `/telegram/integration_bot/webhook`

## Master bot
- Uses inline callback main menu.
- Valid menu callbacks do not fall through to `/help` fallback.
- Legacy request-card callbacks are compatibility-mapped and refresh the card UX.

## Client clarification routing
- Telegram-source requests send outbound clarification back to Telegram first.
- Fallback to MAX is allowed only if a real `maxId` exists.

## Integration bot
- Remains Telegram-only by design.
