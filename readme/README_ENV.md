# Environment Reference

## Required variables
- `WEBAPP_URL`
- `DB_SQLITE_PATH` (preferred, fail-fast if neither it nor the legacy alias is configured)

## Optional but commonly used variables
- `TELEGRAM_CLIENT_BOT_TOKEN`
- `TELEGRAM_MASTER_BOT_TOKEN`
- `TELEGRAM_INTEGRATION_BOT_TOKEN`
- `MASTER_BOT_ADMIN_IDS`
- `INTERNAL_ADMIN_WHITELIST`
- `TELEGRAM_MASTERS_CHAT_ID`
- `TELEGRAM_DEBUG_CHAT_ID`
- `TELEGRAM_CHANNEL_URL`
- `WEBAPP_DEDUPE_WINDOW_MS`
- `WEBAPP_RATE_LIMIT_WINDOW_MS`
- `WEBAPP_RATE_LIMIT_MAX`
- `WEBHOOK_RATE_LIMIT_WINDOW_MS`
- `WEBHOOK_RATE_LIMIT_MAX`
- `SCHEDULER_INTERVAL_MS`
- `SCHEDULER_BATCH_SIZE`
- `SCHEDULER_MAX_ATTEMPTS`
- `SCHEDULER_STUCK_TIMEOUT_MS`
- `FEEDBACK_REQUEST_DELAY_MINUTES`

## Legacy aliases still accepted
- `DB_FILE_PATH` → legacy alias for `DB_SQLITE_PATH`
- `WEBAPP_TELEGRAM_CHANNEL_LINK` → alias for `TELEGRAM_CHANNEL_URL`
- `INTERNAL_ADMIN_WHITELIST_IDS` → alias for `INTERNAL_ADMIN_WHITELIST`

## MAX-specific
- `MAX_ENABLED`
- `MAX_CLIENT_BOT_TOKEN`
- `MAX_MASTER_BOT_TOKEN`
- `MAX_WEBHOOK_SECRET`
- `MAX_WEBHOOK_BASE_URL` (optional explicit public base for MAX webhook subscription reconciliation)
- `MAX_MASTER_BOT_ADMIN_IDS`
- `MAX_WEBAPP_URL`
- `MAX_BOT_NAME`
- `MAX_DEEPLINK_BASE_URL`

## Operational tuning
- rate limits
- dedupe window
- scheduler interval/batch/max-attempts/stuck-timeout
- feedback delay

## Future-facing / compatibility variables
`DB_DRIVER`, `DB_URL`, `QUEUE_DRIVER`, `ONE_C_WEBHOOK_SECRET`, `ONE_C_SYNC_ENABLED`, `ENABLE_INTEGRATION_WORKER`, `INTEGRATION_RETRY_MAX`, `INTEGRATION_RETRY_DELAY_SECONDS`, `MAX_DIAGNOSTICS_ENABLED`.

## Runtime env audit
- `loadConfig()` now classifies env vars into required / optional / legacy buckets.
- Unknown configured env vars with platform-related prefixes are surfaced in `config.envAudit.unknownConfigured`.
- Missing required variables throw during startup when `CONFIG_STRICT=true` or `NODE_ENV=production`.
