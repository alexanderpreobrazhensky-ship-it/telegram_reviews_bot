# Security

## Access control
- `MASTER_BOT_ADMIN_IDS` and `MAX_MASTER_BOT_ADMIN_IDS` bootstrap admin access.
- Additional master/manager users are persisted in `staff_users` and granted/revoked only through master-bot access flow.
- Internal admin routes rely on `INTERNAL_ADMIN_WHITELIST`.

## Secret handling
- Diagnostics and bot-facing status screens mask tokens and secrets.
- `MAX_WEBHOOK_SECRET` is required for MAX webhook validation when MAX is enabled.
- AI env is visible in diagnostics only in masked form.

## Data constraints
- Phone numbers are normalized to 10 digits without `+7/8`.
- Outbound client clarification never uses email as a fallback channel.
- Channel fallback is allowed only when a real `maxId` or `telegramId` exists.

## Operational risks
- Internal routes are still simple env-allowlist endpoints.
- Bot identity is provider payload-based, not a full IAM system.
- SQLite file access should be restricted by deployment filesystem permissions.


## AI security notes
- AI secrets are never printed raw in diagnostics/logs.
- Proxy/OpenAI/DeepSeek secrets are masked in admin diagnostics.
- AI admin surfaces are restricted to admin-only in Master bot.
