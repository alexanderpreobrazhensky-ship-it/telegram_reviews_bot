# Environment Reference

## Canonical variables
- `WEBAPP_URL`
- `DB_SQLITE_PATH` (preferred)
- `TELEGRAM_CLIENT_BOT_TOKEN`
- `TELEGRAM_MASTER_BOT_TOKEN`
- `MASTER_BOT_ADMIN_IDS`

## Legacy aliases still accepted
- `DB_FILE_PATH` → legacy alias for `DB_SQLITE_PATH`
- `WEBAPP_TELEGRAM_CHANNEL_LINK` → alias for `TELEGRAM_CHANNEL_URL`
- `INTERNAL_ADMIN_WHITELIST_IDS` → alias for `INTERNAL_ADMIN_WHITELIST`

## MAX-specific
- `MAX_ENABLED`
- `MAX_CLIENT_BOT_TOKEN`
- `MAX_MASTER_BOT_TOKEN`
- `MAX_WEBHOOK_SECRET`
- `MAX_MASTER_BOT_ADMIN_IDS`
- `MAX_WEBAPP_URL`
- `MAX_BOT_NAME`
- `MAX_DEEPLINK_BASE_URL`

## Operational tuning
- rate limits
- dedupe window
- scheduler interval/batch/max-attempts/stuck-timeout
- feedback delay

## Placeholder or future-facing vars
`DB_DRIVER`, `DB_URL`, `QUEUE_DRIVER`, `ONE_C_WEBHOOK_SECRET`, `ONE_C_SYNC_ENABLED`, `ENABLE_INTEGRATION_WORKER`.
