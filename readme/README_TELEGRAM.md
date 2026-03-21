# Telegram

## Active routes
- `/telegram/client_bot/webhook`
- `/telegram/master_bot/webhook`
- `/telegram/integration_bot/webhook`

## Roles
- Client bot: intake, quick flows, feedback, Mini App launch.
- Master bot: request operations, access control, quality-case actions, reporting.
- Integration bot: event inspection, retry, ignore.

## Access model
- `MASTER_BOT_ADMIN_IDS` bootstraps admin access.
- Additional roles are granted via bot access flow and persisted in SQLite.
- Integration bot remains Telegram-only.
