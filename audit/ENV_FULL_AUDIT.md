# ENV Full Audit

## Scope
All environment variables read by the active Node runtime, their deploy criticality, runtime effect, legacy aliases, and variables that are present only as placeholders.

## Current state
- The canonical env loader is `src/infrastructure/config/index.js`.
- SQLite path resolution also reads env directly inside `src/infrastructure/db/index.js`.
- `MASTER_BOT_ADMIN_IDS` and `MAX_MASTER_BOT_ADMIN_IDS` bootstrap admin access; internal admin pages additionally honor `INTERNAL_ADMIN_WHITELIST`.
- `DB_SQLITE_PATH` is canonical; `DB_FILE_PATH` still works as a legacy alias.

## Confirmed facts
### Production-critical / required in the current Node-first path
- `WEBAPP_URL`
- `DB_SQLITE_PATH` or legacy `DB_FILE_PATH`
- `TELEGRAM_CLIENT_BOT_TOKEN` for outbound Telegram client-bot delivery
- `TELEGRAM_MASTER_BOT_TOKEN` for Telegram master bot and masters-chat duplication
- `MASTER_BOT_ADMIN_IDS` for Telegram admin bootstrap

### Required only when MAX routes are intended to work in production
- `MAX_ENABLED=true`
- `MAX_CLIENT_BOT_TOKEN`
- `MAX_MASTER_BOT_TOKEN`
- `MAX_WEBHOOK_SECRET`
- `MAX_MASTER_BOT_ADMIN_IDS`
- `MAX_WEBAPP_URL` is not strictly required because it falls back to `WEBAPP_URL`, but a dedicated value is recommended

### Optional but operationally important
- `PORT`
- `TELEGRAM_INTEGRATION_BOT_TOKEN`
- `TELEGRAM_MASTERS_CHAT_ID`
- `TELEGRAM_CHANNEL_URL`
- `WEBHOOK_RATE_LIMIT_WINDOW_MS`
- `WEBHOOK_RATE_LIMIT_MAX`
- `WEBAPP_RATE_LIMIT_WINDOW_MS`
- `WEBAPP_RATE_LIMIT_MAX`
- `WEBAPP_DEDUPE_WINDOW_MS`
- `FEEDBACK_REQUEST_DELAY_MINUTES`
- `SCHEDULER_INTERVAL_MS`
- `SCHEDULER_BATCH_SIZE`
- `SCHEDULER_MAX_ATTEMPTS`
- `SCHEDULER_STUCK_TIMEOUT_MS`
- `MAX_BOT_NAME`
- `MAX_DEEPLINK_BASE_URL`
- `MAX_DIAGNOSTICS_ENABLED`

### Placeholders / partial usage / future-facing
- `DB_DRIVER`
- `DB_URL`
- `QUEUE_DRIVER`
- `ONE_C_WEBHOOK_SECRET`
- `ONE_C_SYNC_ENABLED`
- `EMAIL_IMPORT_ENABLED`
- `ENABLE_INTEGRATION_WORKER`
- `INTEGRATION_RETRY_MAX`
- `INTEGRATION_RETRY_DELAY_SECONDS`
- `TELEGRAM_DEBUG_CHAT_ID`

### Deprecated aliases / legacy names
- `DB_FILE_PATH` → legacy alias for `DB_SQLITE_PATH`
- `INTERNAL_ADMIN_WHITELIST_IDS` → legacy alias for `INTERNAL_ADMIN_WHITELIST`
- `WEBAPP_TELEGRAM_CHANNEL_LINK` → legacy alias for `TELEGRAM_CHANNEL_URL`

## Risks
- `MAX_ENABLED` does not prevent route registration; MAX routes still exist and return explicit rejections if disabled or misconfigured.
- `MAX_MASTER_BOT_ADMIN_IDS` is genuinely used for MAX admin bootstrap, so leaving it empty blocks MAX master access.
- `ONE_C_WEBHOOK_SECRET`, `ENABLE_INTEGRATION_WORKER`, and `DB_URL` can mislead operators into assuming stronger integration or multi-driver support than currently exists.
- If only `DB_FILE_PATH` is set and it ends with `.json`, SQLite silently uses the same basename with `.sqlite` while optionally importing legacy JSON once.

## Gaps
- There is no single runtime endpoint that dumps the full env registry; documentation must stay aligned manually.
- Some env flags are descriptive rather than authoritative feature toggles.
- The code has no startup hard-fail for missing Telegram bot tokens; some flows degrade to “route works, outbound delivery skipped.”

## Legacy / dead / misleading parts
- `DB_URL` and `QUEUE_DRIVER` are not connected to actual alternate drivers.
- `ENABLE_INTEGRATION_WORKER` suggests a separate worker, but the scheduler remains in-process.
- `WEBAPP_TELEGRAM_CHANNEL_LINK` and `INTERNAL_ADMIN_WHITELIST_IDS` are transitional aliases only.

## Recommendations
1. Standardize deploy docs and platform secrets on `DB_SQLITE_PATH`, keeping `DB_FILE_PATH` only as a compatibility alias.
2. Treat `MAX_WEBHOOK_SECRET` as mandatory whenever MAX is exposed publicly.
3. Remove or clearly mark placeholder env variables if they remain unused across another release.
4. Consider startup warnings or hard-fails for missing master/client bot tokens in the production profile.

## Confidence level
High for the active Node runtime env registry; medium for legacy Python env tails because they are intentionally not part of the canonical deploy contract.

## Follow-up checks
- Verify live BotHost env values against this registry before each deploy.
- If 1C auth middleware is added later, reclassify `ONE_C_WEBHOOK_SECRET` from placeholder to enforced.
