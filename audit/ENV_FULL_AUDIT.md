# ENV Full Audit

## Scope
All environment variables read by the current Node-first runtime, split into required, optional, legacy, dead-looking, and partially used variables, with emphasis on production impact.

## Current state
- The canonical env loader is `src/infrastructure/config/index.js`.
- SQLite path resolution also reads env directly inside `src/infrastructure/db/index.js`, so DB path behavior must be described from both files.
- Strict fail-fast applies only when `CONFIG_STRICT=true` or when `NODE_ENV=production` triggers strict mode and required env values are missing.
- The current required baseline in code is narrow: `WEBAPP_URL` plus `DB_SQLITE_PATH` or legacy `DB_FILE_PATH`.

## Confirmed facts
### Required env in the current code path
- `WEBAPP_URL`
  - Purpose: canonical Telegram WebApp base URL and fallback for MAX WebApp URLs.
  - Used where: config loader, WebApp runtime injection, bot mini-app link building.
  - Required or optional: required by config audit; missing in strict mode throws.
  - Runtime impact: wrong/missing value breaks WebApp deep links and injected runtime URLs.
  - Legacy risk: none, but production can silently use `https://example.com` outside strict mode.
- `DB_SQLITE_PATH`
  - Purpose: canonical SQLite database file path.
  - Used where: config loader and DB module path resolution.
  - Required or optional: required by config audit unless legacy alias is present.
  - Runtime impact: defines where persistent data is stored.
  - Legacy risk: can be shadowed by `DB_FILE_PATH` assumptions if operators still think in JSON terms.

### Legacy-compatible required alias
- `DB_FILE_PATH`
  - Purpose: legacy alias for DB location.
  - Used where: config loader and DB module fallback path resolution.
  - Required or optional: optional alias, but effectively satisfies the DB-path requirement.
  - Runtime impact: if it ends with `.json`, the runtime converts the active DB path to `.sqlite`; JSON may still be imported from the legacy file path.
  - Legacy risk: highest env drift risk in the current stack because operators may assume JSON remains the primary store.

### Operationally important Telegram env
- `TELEGRAM_CLIENT_BOT_TOKEN`
  - Purpose: Telegram client bot outbound messaging and feedback-request delivery.
  - Used where: config loader, app bootstrap warnings, client bot messaging, scheduler feedback sends.
  - Required or optional: optional in code, but required for full Telegram client-bot functionality.
  - Runtime impact: missing token does not stop boot, but outbound Telegram delivery fails or is skipped.
  - Legacy risk: none.
- `TELEGRAM_MASTER_BOT_TOKEN`
  - Purpose: Telegram master bot outbound messages and masters-chat duplication.
  - Used where: config loader, server duplicate-to-masters flow, master bot responses.
  - Required or optional: optional in code, operationally required for Telegram master workflows.
  - Runtime impact: master bot can accept webhooks but cannot respond correctly without the token.
  - Legacy risk: none.
- `TELEGRAM_INTEGRATION_BOT_TOKEN`
  - Purpose: Telegram integration bot replies.
  - Used where: config loader and integration bot message delivery.
  - Required or optional: optional unless integration bot is used.
  - Runtime impact: integration bot commands can parse input but fail to reply without the token.
  - Legacy risk: none.
- `MASTER_BOT_ADMIN_IDS`
  - Purpose: bootstrap admin IDs for Telegram master bot access and indirect internal admin authorization.
  - Used where: config loader, master bot actor resolution, internal admin whitelist composition.
  - Required or optional: optional in config, operationally required for initial Telegram master administration.
  - Runtime impact: empty value blocks env-bootstrapped Telegram admin access.
  - Legacy risk: none.
- `TELEGRAM_MASTERS_CHAT_ID`
  - Purpose: duplicate newly created WebApp requests into a Telegram masters chat.
  - Used where: config loader and `duplicateToMastersChat()`.
  - Required or optional: optional.
  - Runtime impact: when absent, duplication is skipped.
  - Legacy risk: none.
- `TELEGRAM_DEBUG_CHAT_ID`
  - Purpose: read into config only.
  - Used where: config loader.
  - Required or optional: optional.
  - Runtime impact: currently no direct runtime effect in the active code path.
  - Legacy risk: medium because it looks live but is effectively unused.
- `TELEGRAM_CHANNEL_URL`
  - Purpose: channel CTA URL shown in WebApp result screens.
  - Used where: config loader and runtime HTML injection.
  - Required or optional: optional.
  - Runtime impact: controls the Telegram-channel buttons shown after submit.
  - Legacy risk: low.

### Operationally important MAX env
- `MAX_ENABLED`
  - Purpose: acceptance gate for MAX webhook processing.
  - Used where: config loader, bootstrap warnings, MAX webhook validation, health endpoint.
  - Required or optional: optional globally, required for MAX to function.
  - Runtime impact: MAX routes are still registered even when false, but validation rejects requests with `MAX_DISABLED`.
  - Legacy risk: medium because it is not a route-registration toggle.
- `MAX_CLIENT_BOT_TOKEN`
  - Purpose: outbound MAX client-bot messages and MAX client webhook replies.
  - Used where: config loader, bootstrap warnings, client bot MAX route, scheduler feedback sends.
  - Required or optional: optional globally, required for live MAX client flow.
  - Runtime impact: MAX client route rejects when missing and MAX outbound sends fail.
  - Legacy risk: none.
- `MAX_MASTER_BOT_TOKEN`
  - Purpose: outbound MAX master-bot replies.
  - Used where: config loader, bootstrap warnings, MAX master route.
  - Required or optional: optional globally, required for live MAX master flow.
  - Runtime impact: MAX master route rejects when missing.
  - Legacy risk: none.
- `MAX_WEBHOOK_SECRET`
  - Purpose: shared-secret validation for MAX webhooks.
  - Used where: config loader, bootstrap warnings, MAX security validator.
  - Required or optional: optional globally, required whenever MAX webhooks are exposed.
  - Runtime impact: missing or wrong secret causes 503/403 rejection of MAX webhook requests.
  - Legacy risk: none.
- `MAX_MASTER_BOT_ADMIN_IDS`
  - Purpose: bootstrap MAX master-bot admin IDs.
  - Used where: config loader, master bot actor resolution, internal admin whitelist composition.
  - Required or optional: optional globally, required for initial MAX master administration.
  - Runtime impact: empty value blocks env-bootstrapped MAX admin access.
  - Legacy risk: none.
- `MAX_WEBAPP_URL`
  - Purpose: MAX-specific WebApp base URL.
  - Used where: config loader and MAX mini-app link building.
  - Required or optional: optional because it falls back to `WEBAPP_URL`.
  - Runtime impact: controls the URL MAX users receive for mini-app launches.
  - Legacy risk: low, but fallback behavior can hide missing dedicated config.
- `MAX_BOT_NAME`
  - Purpose: build MAX bot/deep links when direct base URL is not enough.
  - Used where: config loader and `buildMaxBotLink()`/`buildMaxMiniAppLink()`.
  - Required or optional: optional.
  - Runtime impact: improves MAX deep-link generation.
  - Legacy risk: none.
- `MAX_DEEPLINK_BASE_URL`
  - Purpose: read into runtime injection config.
  - Used where: config loader and HTML runtime injection.
  - Required or optional: optional.
  - Runtime impact: currently informational/runtime-injected; not the main mini-app URL builder.
  - Legacy risk: medium because it sounds more authoritative than it currently is.
- `MAX_DIAGNOSTICS_ENABLED`
  - Purpose: stored in config as a diagnostics toggle placeholder.
  - Used where: config loader.
  - Required or optional: optional.
  - Runtime impact: no direct enforcement found in the active server routes.
  - Legacy risk: medium.

### Internal/admin env
- `INTERNAL_ADMIN_WHITELIST`
  - Purpose: explicit allowlist for internal HTML/admin routes.
  - Used where: config loader and internal-route auth.
  - Required or optional: optional.
  - Runtime impact: enables `/internal/requests`, `/internal/export`, and internal POST actions for listed IDs.
  - Legacy risk: low.
- `INTERNAL_ADMIN_WHITELIST_IDS`
  - Purpose: legacy alias for `INTERNAL_ADMIN_WHITELIST`.
  - Used where: config loader.
  - Required or optional: optional legacy alias.
  - Runtime impact: same as above.
  - Legacy risk: medium because it preserves old naming.

### Timing, rate-limit, and scheduler env
- `WEBAPP_DEDUPE_WINDOW_MS`, `WEBAPP_RATE_LIMIT_WINDOW_MS`, `WEBAPP_RATE_LIMIT_MAX`, `WEBHOOK_RATE_LIMIT_WINDOW_MS`, `WEBHOOK_RATE_LIMIT_MAX`, `FEEDBACK_REQUEST_DELAY_MINUTES`, `SCHEDULER_INTERVAL_MS`, `SCHEDULER_BATCH_SIZE`, `SCHEDULER_MAX_ATTEMPTS`, `SCHEDULER_STUCK_TIMEOUT_MS`
  - Purpose: tune dedupe, rate limiting, feedback scheduling, and task processing.
  - Used where: config loader; scheduler settings are passed from `app.js`; dedupe and rate limits are applied in the server and DB logic.
  - Required or optional: optional.
  - Runtime impact: directly changes request throttling and task execution behavior.
  - Legacy risk: low.

### Partially used / placeholder env
- `PORT`, `NODE_ENV`, `CONFIG_STRICT`, `INTEGRATION_RETRY_MAX`, `INTEGRATION_RETRY_DELAY_SECONDS`, `ONE_C_SYNC_ENABLED`, `EMAIL_IMPORT_ENABLED`
  - These are parsed and exposed in config, and some affect derived behavior, but not every value has a broad runtime surface today.
- `DB_DRIVER`, `DB_URL`, `QUEUE_DRIVER`, `ONE_C_WEBHOOK_SECRET`, `ENABLE_INTEGRATION_WORKER`
  - These are present in config as capability placeholders or future extension points, not as active alternative runtime drivers or auth enforcement.

### Dead or near-dead env from the current Node code perspective
- No env is completely dead if it is parsed into config, but `TELEGRAM_DEBUG_CHAT_ID`, `MAX_DIAGNOSTICS_ENABLED`, `DB_DRIVER`, `DB_URL`, `QUEUE_DRIVER`, `ONE_C_WEBHOOK_SECRET`, and `ENABLE_INTEGRATION_WORKER` have little or no direct enforcement in the active request path.

## What changed after modernization
- The env contract is now centered on a Node-first runtime with SQLite, not on Python services or JSON-first persistence.
- `DB_SQLITE_PATH` is now the canonical database variable; `DB_FILE_PATH` is retained only for compatibility.
- MAX env handling is now explicit and guarded by route-level validation rather than assumed.
- WebApp and scheduler tuning env are now part of the active runtime path instead of aspirational documentation.

## Remaining gaps
- There is no single endpoint that safely lists all resolved env values for operators.
- The code still accepts several placeholder env names that can confuse deployers about what is truly implemented.
- Outside strict mode, some missing env values degrade to fallbacks instead of failing fast.

## Risks
- `DB_FILE_PATH` still creates deploy confusion because `.json` values lead to `.sqlite` runtime paths plus optional JSON import.
- Missing bot tokens do not always stop the app from booting, so runtime health can look better than actual delivery readiness.
- `MAX_ENABLED=false` does not hide MAX routes; it only makes them reject, which can confuse operators and probes.
- Internal admin access depends on simple ID allowlisting, so misconfigured env values can overexpose internal pages.

## Legacy / dead / misleading parts
- `DB_FILE_PATH`, `INTERNAL_ADMIN_WHITELIST_IDS`, and `WEBAPP_TELEGRAM_CHANNEL_LINK` are legacy names/aliases.
- `DB_DRIVER`, `DB_URL`, and `QUEUE_DRIVER` imply pluggability not present in the active production runtime.
- `ONE_C_WEBHOOK_SECRET` exists in config but is not enforced on `/api/integrations/one-c/*` routes.
- `ENABLE_INTEGRATION_WORKER` suggests a separate worker model, but the scheduler remains in-process.

## Confidence level
High for env values read by code; medium for which values are configured in live production, because no runtime secret inspection was performed.

## Recommended follow-up checks
- Compare the live BotHost env set against this registry before the next deploy.
- Decide whether to hard-fail on missing Telegram/MAX tokens in stricter production profiles.
- Consider removing or clearly annotating placeholder env names that are not enforced today.
