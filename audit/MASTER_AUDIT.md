# Master Audit
## Purpose
- This file is the единственный and canonical source of audit information for the project.
- All historical audit content from the former split files under `audit/` is preserved below without removing conclusions, risks, confirmed facts, or follow-up checks.
- Any future audit update must be made only in `audit/MASTER_AUDIT.md`.
- The split audit contour was intentionally removed to avoid drift and duplicate sources of truth.

## Navigation
- [DOCUMENTATION_CONSISTENCY_AUDIT.md](#documentation-consistency-audit)
- [ENV_FULL_AUDIT.md](#env-full-audit)
- [MASTER_AUDIT_FOR_EXTERNAL_AI.md](#master-audit-for-external-ai)
- [MAX_AUDIT.md](#max-audit)
- [PERSISTENCE_AUDIT.md](#persistence-audit)
- [POST_DEPLOY_VERIFICATION_AUDIT.md](#post-deploy-verification-audit)
- [REPOSITORY_FULL_AUDIT.md](#repository-full-audit)
- [RUNTIME_AUDIT.md](#runtime-audit)
- [SECURITY_AUDIT.md](#security-audit)
- [TELEGRAM_AUDIT.md](#telegram-audit)
- [TESTING_AUDIT.md](#testing-audit)
- [WEBAPP_AUDIT.md](#webapp-audit)

## Documentation rule
1. `audit/MASTER_AUDIT.md` is the only active audit document in the repository.
2. Do not recreate split audit files under `audit/`.
3. When audit information changes, append or edit the relevant section in this file only.
4. If external or internal docs mention audit materials, they must link only to `audit/MASTER_AUDIT.md`.

---

## DOCUMENTATION_CONSISTENCY_AUDIT.md
<a id="documentation-consistency-audit"></a>

### Preserved content

# Documentation Consistency Audit

## Scope
Consistency between current code, audit files, and `readme/` documentation, with emphasis on eliminating outdated architectural descriptions.

## Current state
- The documentation set now consistently describes the project as Node-first, SQLite-backed, and centered on `app.js` + `src/server/index.js`.
- Audit files live under `audit/`; operational docs live under `readme/`.
- The refreshed audit set uses consistent terminology for Telegram, MAX, WebApp, persistence, runtime, and security.

## Confirmed facts
### Confirmed by direct repo inspection
- `readme/README_DEPLOY.md`, `README_RUNTIME.md`, `README_ENV.md`, `README_PERSISTENCE.md`, `README_WEBAPP.md`, and `README_MAX.md` all align with the active Node-first runtime.
- The refreshed audit files now align with the code-confirmed reality that SQLite is active and JSON is compatibility-only.
- Telegram integration bot is consistently described as Telegram-only.
- MAX is consistently described as embedded in the same Node project, not as a separate deployment.
- `review.html` and `public/index.html` were left untouched.

### Previously stale claims removed or downgraded
- Python-first production descriptions.
- JSON-first persistence descriptions.
- Blanket statements that MAX is purely unimplemented.
- Blanket statements that older phone-input issues are still confirmed production facts.
- Claims that route maps outside `src/server/index.js` are authoritative.

## What changed after modernization
- Documentation now follows the current runtime path instead of the broad historical tree.
- Audit files now distinguish code-confirmed facts from runtime-only assumptions.
- Terminology is synchronized across repository, env, runtime, persistence, WebApp, Telegram, MAX, security, testing, and post-deploy audits.
- The external-agent starter document is now the Markdown file `audit/MASTER_AUDIT.md`.

## Remaining gaps
- The machine-readable JSON mirror previously present under `audit/` could drift if maintained separately.
- There is still no automated doc-vs-code consistency test.
- Legacy repository folders can still attract future documentation drift if someone documents from a superficial tree scan.

## Risks
- If future runtime changes land without parallel audit/readme updates, drift can reappear quickly.
- Legacy and placeholder files/env names still create documentation ambiguity.
- Operators may still rely on old external notes not stored in the repo.

## Legacy / dead / misleading parts
- Any document describing the project as Python-first or legacy-first is stale.
- Any document describing JSON as the current primary production store is stale.
- Any document that generalizes session-specific WebApp issues into repo-wide production blockers without evidence is misleading.
- The older JSON-form external-agent audit mirror is no longer needed as a primary source of truth.

## Confidence level
High for repository-internal documentation consistency after this rewrite; medium for external/off-repo documentation because it was not inspected.

## Recommended follow-up checks
- Remove or regenerate any machine-readable audit mirror if you want to keep only one external-agent source of truth.
- Update audit/readme files in the same PR whenever runtime or env behavior changes.
- Consider adding a lightweight CI check that confirms required audit files exist only under `audit/`.

---

## ENV_FULL_AUDIT.md
<a id="env-full-audit"></a>

### Preserved content

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

---

## MASTER_AUDIT_FOR_EXTERNAL_AI.md
<a id="master-audit-for-external-ai"></a>

### Preserved content

# Master Audit for External AI

## Scope
Compact source of truth for the next GPT/AI agent that needs to reason about the repository and then perform runtime checks without re-discovering the whole project.

## Current state
- Production reality is Node-first.
- Entrypoint: `app.js`.
- Main server/runtime router: `src/server/index.js`.
- Main config loader: `src/infrastructure/config/index.js`.
- Main persistence module: `src/infrastructure/db/index.js`.
- Main WebApp runtime: `public/webapp.js` served through `public/index.html` with server-side runtime injection.
- Telegram client bot, Telegram master bot, Telegram integration bot, MAX client bot, and MAX master bot all live in the same Node service.

## Confirmed facts
### Production reality summary
- This is not a Python-first project in production terms.
- This is not a JSON-first project in production terms.
- BotHost and Docker point at `app.js`.
- SQLite is the active persistence engine.
- MAX is embedded in the same runtime, not deployed as a separate project.

### Active runtime path summary
- Bootstrap: `app.js`.
- HTTP server and route map: `src/server/index.js`.
- Bot handlers: `src/interfaces/client_bot/index.js`, `src/interfaces/master_bot/index.js`, `src/interfaces/integration_bot/index.js`.
- MAX security gate: `src/interfaces/shared/maxSecurity.js`.
- Shared messaging/deeplink utilities: `src/infrastructure/messaging/index.js`.
- WebApp client logic: `public/webapp.js`.

### Env reality summary
- Truly required baseline in code: `WEBAPP_URL` and `DB_SQLITE_PATH` or `DB_FILE_PATH` in strict mode.
- Operationally critical Telegram env: `TELEGRAM_CLIENT_BOT_TOKEN`, `TELEGRAM_MASTER_BOT_TOKEN`, `MASTER_BOT_ADMIN_IDS`.
- Operationally critical MAX env when MAX is enabled: `MAX_ENABLED`, `MAX_CLIENT_BOT_TOKEN`, `MAX_MASTER_BOT_TOKEN`, `MAX_WEBHOOK_SECRET`, `MAX_MASTER_BOT_ADMIN_IDS`.
- Canonical DB env is `DB_SQLITE_PATH`; `DB_FILE_PATH` is legacy compatibility.

### Persistence reality summary
- Active DB is SQLite.
- Legacy JSON import path still exists and can run on first empty init.
- If `DB_FILE_PATH` ends in `.json`, runtime DB still becomes `.sqlite`.
- Request dedupe is heuristic, not hard uniqueness.

### Telegram / MAX / WebApp reality summary
- Telegram is the more mature/proven channel.
- MAX has real code paths and tests, but live readiness still needs runtime confirmation.
- Integration bot is Telegram-only.
- WebApp forms are active and use a 10-digit phone model.
- WebApp identity uses provider runtime objects / submitted IDs and is not cryptographically verified.

### Confirmed risks summary
- Unauthenticated integration/reporting/mutation endpoints at app-layer.
- Telegram webhook requests lack in-app secret verification.
- Internal admin pages use allowlisted IDs rather than stronger auth.
- In-memory sessions and rate limits are instance-local.
- Deploy/runtime drift is still possible if env or BotHost config is stale.

## What changed after modernization
- Node-first runtime is now the canonical truth.
- SQLite-first persistence replaced JSON-first descriptions.
- MAX should now be treated as an embedded supported contour, not as a non-existent one.
- Phone-input and request-validation narratives now match the fixed 10-digit implementation.

## Remaining gaps
- No live runtime confirmation is embedded in the repo.
- No cryptographic WebApp identity verification.
- No auth on several operational/integration endpoints.
- No proof here of actual BotHost persistent-volume behavior.

## Risks
- A stale production env can still undermine the code-confirmed architecture.
- Multi-instance scaling would require rethinking scheduler, rate limiting, dedupe, and session handling.
- External platform configuration remains outside repo proof.

## Legacy / dead / misleading parts
- Do not start analysis from `bots/**`, `services/**`, `shared/clients_registry.py`, or `legacy/index.js`.
- Do not treat `src/interfaces/webapp/routes.js` as the real route source.
- Do not describe the project as Python-first, JSON-first, or legacy-first.
- Do not describe session-specific mini-app anomalies as global blockers unless reproduced.

## Confidence level
High for repository truth; medium for live production truth.

## Recommended follow-up checks
- Check live env values for: `WEBAPP_URL`, `DB_SQLITE_PATH`, `TELEGRAM_CLIENT_BOT_TOKEN`, `TELEGRAM_MASTER_BOT_TOKEN`, `MASTER_BOT_ADMIN_IDS`, `MAX_ENABLED`, `MAX_CLIENT_BOT_TOKEN`, `MAX_MASTER_BOT_TOKEN`, `MAX_WEBHOOK_SECRET`, `MAX_MASTER_BOT_ADMIN_IDS`, `MAX_WEBAPP_URL`.
- Verify `/health`, `/health/db`, and `/health/max` in the live environment.
- Create one Telegram WebApp request and one MAX WebApp request end-to-end.
- Verify Telegram client bot, Telegram master bot, Telegram integration bot, MAX client bot, and MAX master bot with real credentials.
- Confirm SQLite persistence across a real restart/redeploy.
- Check whether unauthenticated integration/reporting endpoints are protected by the production perimeter.

---

## MAX_AUDIT.md
<a id="max-audit"></a>

### Preserved content

# MAX Audit

## Scope
MAX webhook routes, env usage, secret protection, identity assumptions, callback/message handling, mini-app linkage, and current readiness level.

## Current state
- MAX support is embedded in the same Node runtime as Telegram; there is no separate MAX project.
- Two MAX webhook routes exist: client bot and master bot.
- MAX readiness is materially better than a placeholder, but still more runtime-dependent and less proven than Telegram.

## Confirmed facts
### Confirmed
- MAX client webhook route: `/max/client_bot/webhook`.
- MAX master webhook route: `/max/master_bot/webhook`.
- Both MAX routes call `validateMaxWebhookRequest()` before business logic is processed.
- MAX validation requires: `MAX_ENABLED=true`, presence of the relevant MAX bot token, presence of `MAX_WEBHOOK_SECRET`, exact `X-Max-Bot-Api-Secret` match, and object-shaped payload.
- Secret-bearing headers are sanitized before logging.
- MAX client and master flows reuse the same core request/master services used by Telegram where possible.
- MAX outbound messaging and callback answering are implemented against `https://platform-api.max.ru`.
- MAX mini-app URLs are built from `MAX_WEBAPP_URL` or `WEBAPP_URL`, with optional `MAX_BOT_NAME` and deep-link payload handling.
- WebApp runtime can detect a MAX context and submit requests with `sourceChannel = max_webapp` plus `maxId`.

### Partially confirmed
- MAX identity is taken from webhook payloads and from `MAX.WebApp.initDataUnsafe`, which is code-confirmed but not cryptographically validated by this repo.
- MAX contact-request support is implemented in the WebApp, but real provider behavior still needs live runtime confirmation.
- MAX master access bootstrap through `MAX_MASTER_BOT_ADMIN_IDS` is implemented, but live correctness depends on actual configured IDs.

### Not confirmed
- Live MAX webhook registration state in the external MAX platform.
- Real delivery success with production MAX tokens.
- Device-specific MAX WebView behavior outside the automated tests.

### Hypothesis only
- It would be too strong to claim full production parity with Telegram based on repository evidence alone.

## What changed after modernization
- MAX is now documented as an embedded, code-backed contour of the Node production runtime rather than a hypothetical add-on.
- Secret validation and route rejection semantics are explicit in code.
- MAX mini-app launch handling is integrated with the shared WebApp shell.
- Earlier blanket statements that MAX is only skeletal are now outdated; the code supports meaningful request and master workflows, though runtime proof remains partial.

## Remaining gaps
- No cryptographic verification of MAX WebApp identity beyond trusted runtime objects.
- No MAX integration bot exists.
- No separate MAX-specific operator broadcast equivalent to Telegram masters-chat duplication is present.
- No live runtime evidence was collected for production MAX webhook registration or outbound delivery.

## Risks
- Misconfiguration of `MAX_ENABLED`, tokens, or webhook secret causes routes to exist but reject traffic.
- Identity spoofing risk remains if downstream logic over-trusts webhook/user payloads or `initDataUnsafe`.
- MAX readiness can be overstated if code-confirmed behavior is confused with live platform confirmation.
- Operational confusion remains possible if MAX env is partially filled and the health endpoint appears superficially okay.

## Legacy / dead / misleading parts
- `MAX_ENABLED` is an acceptance gate, not a route-registration switch.
- MAX should not be described as a separate deployment topology for this project.
- Any stale doc claiming MAX has no meaningful implementation is no longer accurate.

## Confidence level
Medium-high for code-confirmed behavior; medium for real production readiness because live MAX runtime validation was not part of this pass.

## Recommended follow-up checks
- Verify live MAX webhook registration and secret/header behavior.
- Test `/max/client_bot/webhook` and `/max/master_bot/webhook` with real credentials.
- Run live MAX mini-app smoke tests for launch, submit, and callback flows.

---

## PERSISTENCE_AUDIT.md
<a id="persistence-audit"></a>

### Preserved content

# Persistence Audit

## Scope
Current persistence model, SQLite path resolution, schema creation, JSON import compatibility, integrity behavior, and remaining data-loss / duplicate risks.

## Current state
- The active persistence layer is SQLite via `better-sqlite3` in `src/infrastructure/db/index.js`.
- The runtime resolves its active DB path from `DB_SQLITE_PATH`, then legacy `DB_FILE_PATH`, then a default `data/db.sqlite` path.
- If the configured/legacy path ends in `.json`, the active runtime DB path is rewritten to a `.sqlite` filename while the JSON path remains eligible for import.
- Schema creation is automatic and idempotent at startup.

## Confirmed facts
### Confirmed by code
- SQLite is the only implemented active database driver in production code.
- The DB connection enables `journal_mode = WAL`, `synchronous = NORMAL`, and `foreign_keys = ON`.
- `initializeStore()` creates the schema and then conditionally imports legacy JSON when the SQLite store is empty and a legacy JSON file exists.
- `getLegacyJsonPath()` can use `DB_JSON_IMPORT_PATH`; otherwise it derives the path from legacy/default logic.
- Schema includes at least: `clients`, `vehicles`, `requests`, `request_events`, `communications`, `tasks`, `staff_users`, `quality_cases`, `analytics_events`, `recommendations`, `feedback`, `report_snapshots`, and `meta`.
- Clients have a DB-level `CHECK` constraint limiting stored phone values to either `NULL` or exactly 10 digits.
- Requests, analytics events, communications, tasks, quality cases, feedback, and report snapshots are all stored in SQLite and then rehydrated into JS objects.
- The runtime still supports destructive JSON-to-SQLite import and whole-store replacement helpers, which are used in tests and migration-style logic.
- Request duplicate handling is heuristic: new requests are still created, then marked as duplicates if a recent match is found.
- Task processing and reporting snapshots are persisted in SQLite, not in memory-only structures.

### Confirmed by tests
- SQLite file creation, table creation, JSON migration, CRUD persistence, and restart survival are covered by `tests/node/sqlite-persistence.test.js`.

### Confirmed only by runtime/deploy assumption
- The live BotHost filesystem path configured for SQLite is assumed to be persistent.
- The live production DB is assumed to already be on SQLite unless an operator still deploys with a JSON-oriented env mismatch.

### Unresolved / hypothesis only
- There is no runtime evidence in this repo alone that production has completed any needed one-time JSON import already.
- There is no direct proof here that operators are backing up the SQLite file before destructive migration/import operations.

## What changed after modernization
- SQLite is now the canonical persistence layer; JSON is no longer the primary store.
- Initialization now explicitly logs DB runtime info and migration status at boot.
- Request lifecycle state, analytics, quality cases, feedback, tasks, and reporting snapshots are all aligned to the SQLite-backed runtime.
- The project moved from “legacy JSON-first possibility” to “SQLite-first with compatibility import path.”

## Remaining gaps
- There is no formal migration framework with explicit version files.
- There is no built-in backup/restore CLI for operators.
- Some relational links still depend on JSON payload fields in addition to table columns.
- The DB module still exposes destructive helpers that would need careful operational handling if used outside tests.

## Risks
- If production is misconfigured with a legacy JSON path, operators may misunderstand where the active `.sqlite` file is actually written.
- JSON import and `replaceStore()` are destructive operations for target tables.
- Duplicate prevention is advisory, not enforced by a unique DB constraint.
- `synchronous = NORMAL` trades some durability margin for performance.
- Multi-instance deployment would raise integrity risk for scheduler/task claiming and duplicate heuristics unless carefully coordinated.

## Legacy / dead / misleading parts
- `DB_FILE_PATH` and `DB_JSON_IMPORT_PATH` remain legacy-oriented persistence knobs.
- The presence of JSON import logic should not be described as JSON-first persistence anymore.
- `DB_DRIVER` and `DB_URL` are misleading for persistence architecture because alternate DB drivers are not implemented in the active path.

## Confidence level
High for code-confirmed persistence behavior; medium for live production data location and migration state because runtime filesystem inspection was not performed.

## Recommended follow-up checks
- Confirm the live production env points to the intended SQLite file path.
- Verify that the active `.sqlite` file survives restart and redeploy in BotHost.
- Before any migration/import activity, take and test a SQLite backup.
- If request dedupe becomes business-critical, consider unique constraints or stronger idempotency keys.

---

## POST_DEPLOY_VERIFICATION_AUDIT.md
<a id="post-deploy-verification-audit"></a>

### Preserved content

# Post-Deploy Verification Audit

## Scope
Main post-deploy status summary: what modernization was expected to deliver, what is confirmed by code, what still needs runtime verification, and which risks are already reduced versus still open.

## Current state
- The repository now reflects a Node-first production runtime centered on `app.js` and `src/server/index.js`.
- SQLite is the active persistence layer.
- Telegram client/master/integration flows, MAX client/master flows, WebApp forms, internal pages, and reports are all present in the same server runtime.
- Audit documentation has been synchronized to the current code rather than to historical assumptions.

## Confirmed facts
### What should have been in place after modernization
- Node-first production entrypoint.
- SQLite-backed persistence with optional legacy JSON import path.
- Unified server for WebApp, bots, health, reports, and integrations.
- 10-digit phone handling across WebApp, server validation, and persistence.
- MAX embedded in the same Node runtime with secret-protected webhook handling.

### What is confirmed by code right now
- `app.js` is the entrypoint used by package, Docker, and BotHost files.
- `src/server/index.js` serves the active runtime routes.
- DB initialization and schema creation happen at boot.
- Telegram and MAX handlers are registered in the same process.
- WebApp forms and phone logic are aligned with server validation.
- Internal request pages/export and reporting endpoints are present.
- MAX webhook secret validation is implemented.

### What should still be checked by an agent or operator against runtime
- Actual BotHost env values.
- Actual SQLite file location and persistence across restart/redeploy.
- Real Telegram webhook registration and outbound delivery.
- Real MAX webhook registration and outbound delivery.
- Live WebApp behavior in Telegram and MAX clients.

## What changed after modernization
- Old “Python-first” and “JSON-first” descriptions are no longer accurate and were removed from the active audit narrative.
- MAX has moved from vague/aspirational treatment to a concrete code-backed contour with explicit security checks.
- Phone-input and request-validation audits now reflect the fixed 10-digit model rather than earlier looser assumptions.
- The audit set now separates code-confirmed facts from runtime-only assumptions.

## Remaining gaps
- No production runtime evidence was collected in this pass.
- No deploy-time screenshot or live smoke artifact is stored in the repo.
- Integration/reporting endpoints still need a perimeter/auth review in the real deployment.

## Risks
- Production could still differ from code if env or BotHost configuration is stale.
- Unauthenticated integration/reporting/mutation endpoints remain a live concern unless protected externally.
- MAX readiness can still be overstated if live runtime checks are skipped.

## Legacy / dead / misleading parts
- Old audit claims that treated JSON or Python as the primary production reality are obsolete.
- Old audit claims that treated MAX as entirely unimplemented are also obsolete.
- Any session-specific mini-app anomaly should not be generalized into a global production blocker without runtime reproduction.

## Confidence level
High for repository/code truth; medium for actual deployed runtime truth because this pass did not inspect production directly.

## Recommended follow-up checks
- Run the live checks listed in `audit/MASTER_AUDIT.md` after deployment.
- Record the results of `/health`, `/health/db`, `/health/max`, one Telegram request, one MAX request, and one restart-persistence check.
- Re-open security review if integration/reporting endpoints are publicly reachable.

---

## REPOSITORY_FULL_AUDIT.md
<a id="repository-full-audit"></a>

### Preserved content

# Repository Full Audit

## Scope
Repository structure, the real Node-first production contour, supporting files, remaining legacy areas, and files that are still present but are not runtime source of truth.

## Current state
- The active production entrypoint is `app.js`, with the HTTP runtime created in `src/server/index.js`.
- Runtime-critical code is concentrated in `src/core/**`, `src/infrastructure/**`, `src/interfaces/**`, `src/integrations/**`, `public/**`, and the top-level deployment files `package.json`, `Dockerfile`, and `.bothost/entrypoint.conf`.
- The repository still contains historical Python and legacy folders (`bots/**`, `services/**`, `shared/clients_registry.py`, `legacy/index.js`), but they are not referenced by the active Node startup chain.
- Audit artifacts are concentrated under `audit/`, and operational prose docs are concentrated under `readme/`.

## Confirmed facts
### Confirmed by code
- `package.json` declares `main: "app.js"` and `npm start` runs `node app.js`.
- `.bothost/entrypoint.conf` points BotHost at `app.js`.
- `Dockerfile` also starts `node app.js`.
- `app.js` loads config, initializes the SQLite store, creates the HTTP server, and starts the in-process scheduler after `listen()` succeeds.
- `src/server/index.js` is the authoritative route map for health endpoints, internal HTML pages, API routes, static assets, and bot webhooks.
- Production WebApp code is `public/webapp.js`; the server injects runtime configuration into `public/index.html` at response time.
- Telegram client bot, Telegram master bot, Telegram integration bot, MAX client bot, and MAX master bot are all registered from `src/server/index.js` through `src/interfaces/**`.

### Confirmed by deployment-oriented files
- BotHost and container entrypoints both align with the Node-first runtime.
- There is no deployment file in the active contour that points production at the Python folders.

### Still hypothesis only
- The exact runtime contents mounted in the live BotHost instance are not provable from the repository alone.
- The exact set of files copied into the current production release cannot be confirmed without a runtime/deploy inspection.

## What changed after modernization
- P0/P1/P2-era modernization consolidated the production path around Node instead of the earlier mixed/tree-wide perception.
- The server now combines WebApp delivery, bot webhooks, internal operational pages, reports, integrations, and health endpoints in one Node process.
- SQLite-backed persistence under `src/infrastructure/db/index.js` replaced JSON-first persistence as the active source of truth, while keeping one-way JSON import compatibility.
- The audit baseline is now aligned to the active runtime rather than to the broad historical repository tree.

## Remaining gaps
- Legacy folders remain in-place, so a superficial repo scan can still overestimate their production relevance.
- There is no generated runtime manifest that labels directories as active, supporting, or legacy.
- `src/interfaces/webapp/routes.js` and `src/interfaces/webapp/state.js` still exist as lightweight scaffolding, which can mislead readers into treating them as the runtime routing source.

## Risks
- Future contributors may still read `bots/**` or `services/**` as active runtime code unless the Node-first contour is stated explicitly.
- Placeholder infrastructure knobs (`DB_DRIVER`, `DB_URL`, `QUEUE_DRIVER`, `ENABLE_INTEGRATION_WORKER`) can make the repo look more pluggable than it is.
- A deploy/config mismatch could still occur if an operator relies on legacy assumptions rather than the Node-first runtime path.

## Legacy / dead / misleading parts
- `bots/**`, `services/**`, and `shared/clients_registry.py` are legacy/supporting artifacts, not active production runtime.
- `legacy/index.js` is not part of the active startup chain.
- `src/interfaces/webapp/routes.js` and `src/interfaces/webapp/state.js` are not the authoritative route/source-of-truth layer for production WebApp delivery.
- The Python test files and Python service folders should not be used to describe the current production architecture.
- `review.html` and `public/index.html` remain present but were not used as audit rewrite targets.

## Confidence level
High for repository shape and production-relevant code paths; medium for live deploy packaging details because runtime inspection was not part of this pass.

## Recommended follow-up checks
- Verify the live BotHost release really starts from `app.js` and not an older artifact.
- Add a simple active-vs-legacy repository map to reduce future drift.
- If legacy Python folders are no longer needed, archive or clearly mark them to reduce architectural ambiguity.

---

## RUNTIME_AUDIT.md
<a id="runtime-audit"></a>

### Preserved content

# Runtime Audit

## Scope
Entrypoint, startup chain, route registration, scheduler behavior, WebApp delivery, and the boundary between code-confirmed runtime facts and deploy-only assumptions.

## Current state
- The production runtime is a single Node.js HTTP process started from `app.js`.
- The app uses Node's built-in `http` server rather than Express or another framework.
- WebApp routes, API routes, internal pages, health checks, and bot webhooks share the same process.
- The scheduler is in-process and starts only after the server begins listening.

## Confirmed facts
### Confirmed by code
- `app.js` calls `loadConfig()`, logs DB runtime info, initializes the store, creates the server, configures the scheduler, and starts the scheduler inside the `listen()` callback.
- `src/server/index.js` registers bot routes before request handling begins.
- Health endpoints are `/health`, `/health/db`, and `/health/max`.
- Internal operational pages are served at `/internal/requests`, `/internal/requests/:id`, and `/internal/export`.
- Static assets are served directly from `public/` for `/styles.css`, `/webapp.js`, and `/logo.png`.
- WebApp HTML for `/`, `/requests`, `/recommendations`, and the five `/forms/...` routes is always served from `public/index.html` with injected runtime config.
- Webhook requests are subject to an in-memory rate limiter keyed by path and request IP.
- WebApp request creation routes are separately rate-limited and dedupe-checked.
- Scheduler handlers are configured in `app.js`; only `feedback_request` currently has implemented outbound behavior, while `quality_followup`, `recommendation_reminder`, and `maintenance_reminder` are placeholders.

### Confirmed by deployment-oriented files
- BotHost and Docker both point at the same `app.js` startup path.
- The runtime expects a writable filesystem location for SQLite.

### Confirmed only by deployment assumptions, not by repo runtime proof
- BotHost is assumed to preserve the configured SQLite path across restarts/redeploys.
- Telegram and MAX webhook endpoints are assumed to be registered with their external platforms.
- Network egress to Telegram and MAX APIs is assumed to be available in production.

### Unresolved runtime uncertainty
- Whether production runs a single instance or multiple instances is not confirmed from code or deploy files here.
- Whether the live environment uses strict config mode is not confirmed.
- Whether the live deployment exposes integration endpoints publicly or behind additional proxy controls is not confirmed.

## What changed after modernization
- The runtime path is now explicitly Node-first, centralized in `app.js` and `src/server/index.js`.
- Persistence startup is now SQLite-centric, with DB runtime logging and initialization happening before server start.
- WebApp delivery, admin pages, integrations, reporting, and bots now live behind a unified HTTP server instead of appearing as scattered legacy surfaces.
- Scheduler behavior is codified as an in-process runtime responsibility rather than an external worker assumption.

## Remaining gaps
- No process supervisor logic or cluster coordination exists in the repo.
- No startup manifest endpoint summarizes registered routes or enabled contours.
- No separate worker isolates scheduler/task execution from request-handling load.
- In-memory rate limiting and sessions remain instance-local.

## Risks
- Single-process design means webhook bursts, internal reports, and scheduler work share one failure domain.
- In-memory sessions in bot handlers are lost on restart.
- Instance-local rate limiting and scheduler logic can misbehave under uncoordinated horizontal scaling.
- Runtime health endpoints may appear healthy even if outbound bot tokens are missing.

## Legacy / dead / misleading parts
- `src/interfaces/webapp/routes.js` is not the authoritative runtime route map.
- Legacy Python folders describe an older shape and must not be treated as the active runtime contour.
- Placeholder env values such as `ENABLE_INTEGRATION_WORKER` can imply a worker topology that does not exist yet.

## Confidence level
High for code-confirmed runtime flow; medium for production hosting behavior because no live runtime inspection was performed.

## Recommended follow-up checks
- Verify the live process is launched from `app.js` and that scheduler logs appear after server start.
- Confirm persistence survives a real BotHost restart on the configured SQLite path.
- If multi-instance deployment is planned, re-audit scheduler, dedupe, rate limiting, and bot sessions immediately.

---

## SECURITY_AUDIT.md
<a id="security-audit"></a>

### Preserved content

# Security Audit

## Scope
Webhook validation, token handling, internal-route protection, identity trust boundaries, spoofing surface, unauthenticated endpoints, rate limiting, and data-exposure posture.

## Current state
- MAX webhooks have explicit shared-secret validation in code.
- Telegram webhooks do not have comparable in-app secret validation.
- Internal operational HTML routes rely on a simple allowlist of admin IDs provided by env and passed by query/header.
- Several integration/admin-style JSON endpoints remain unauthenticated at the application layer.

## Confirmed facts
### Confirmed by code
- MAX webhook requests are rejected unless `MAX_ENABLED`, token presence, `MAX_WEBHOOK_SECRET`, correct secret header, and valid object payload are present.
- Secret-like MAX headers are masked in logs.
- Webhook routes are protected by an in-memory rate limiter.
- WebApp request-creation routes are protected by a separate in-memory rate limiter.
- Internal HTML pages and internal export/actions require a whitelisted admin ID resolved from header or query parameter.
- `/health`, `/health/db`, and `/health/max` are publicly readable in the current server code.
- `/api/integrations/email`, `/api/integrations/manual`, `/api/integrations/one-c/*`, `/api/integrations/events`, `/api/reports/*`, `/api/requests/:id/assign`, and `/api/requests/:id/status` have no explicit authentication layer in the current server code.
- WebApp/client flows trust submitted `telegramId`, `maxId`, and provider runtime objects without signature verification.
- Telegram webhook routes do not enforce a secret token or provider-signature check in the active code.

### Mitigated / reduced relative to older concerns
- MAX webhook protection is materially stronger than an unprotected open webhook because secret validation is implemented.
- Secret-bearing MAX headers are no longer logged in raw form.
- Webhook and WebApp rate limiting reduce, but do not eliminate, abuse risk.

### Confirmed only by assumption outside the repo
- Reverse-proxy or BotHost perimeter controls may exist, but they are not visible in this codebase.

### Hypothesis only
- It cannot be claimed from the repository alone that production integration endpoints are safe because the hosting perimeter may or may not restrict them.

## What changed after modernization
- MAX secret validation is now explicit and should no longer be listed as a missing control.
- Security documentation now distinguishes reduced/mitigated risks from still-open issues.
- The active threat model is centered on the Node-first runtime, not on historical legacy services.

## Remaining gaps
- No application-layer auth for integration endpoints.
- No cryptographic validation for Telegram or MAX WebApp identity.
- No persistent/shared rate limit store for multi-instance scaling.
- No signed session model for internal pages.

## Risks
- Spoofing risk remains on unauthenticated integration and direct mutation endpoints.
- Telegram webhook requests rely on provider/path secrecy and platform configuration rather than in-app verification.
- Internal admin authorization depends on possession/knowledge of an allowed ID, which is weaker than signed auth.
- Public health endpoints expose useful environment posture such as missing required env and MAX readiness flags.
- Reporting and request-mutation endpoints may be reachable without app-layer auth if external perimeter controls are absent.

## Legacy / dead / misleading parts
- `ONE_C_WEBHOOK_SECRET` exists in config but is not enforced by current 1C routes.
- Placeholder config names can misleadingly imply stronger security controls than are actually active.
- Any stale audit claim saying MAX webhooks are completely unprotected should be removed; the remaining issue is incomplete platform-wide hardening, not absence of MAX validation.

## Confidence level
High for code-confirmed route posture; medium for true production exposure because reverse-proxy/network controls were not inspected.

## Recommended follow-up checks
- Determine whether BotHost or a reverse proxy restricts `/api/integrations/*`, `/api/reports/*`, and mutation endpoints.
- Consider adding auth or shared-secret validation to integration and reporting endpoints.
- Consider Telegram secret-token validation if supported by the deploy platform.
- Review whether public health endpoints should be reduced in production.

---

## TELEGRAM_AUDIT.md
<a id="telegram-audit"></a>

### Preserved content

# Telegram Audit

## Scope
Telegram client bot, master bot, integration bot, Telegram WebApp relationship, callback flows, access logic, supported commands, and Telegram-specific runtime limitations.

## Current state
- Telegram remains a first-class production channel inside the Node runtime.
- Three Telegram webhook routes exist: client bot, master bot, and integration bot.
- Telegram WebApp launch links are generated from `WEBAPP_URL` and used in client bot menus.
- Telegram remains the only implemented channel for the integration bot.

## Confirmed facts
### Confirmed by code
- Client bot webhook route: `/telegram/client_bot/webhook`.
- Master bot webhook route: `/telegram/master_bot/webhook`.
- Integration bot webhook route: `/telegram/integration_bot/webhook`.
- Client bot supports `/start`, `/help`, quick-request callbacks, free-text request starts, full-name collection, phone collection, native contact intake, and feedback parsing for `1`-`5` style replies.
- Telegram client bot uses inline/keyboards to open the WebApp and to collect contact data.
- Requests created from Telegram chat are stored with Telegram-oriented source channels such as `telegram_chat`.
- Master bot resolves actor access from `MASTER_BOT_ADMIN_IDS` plus DB-backed staff users, and supports request/status/comment/access/reporting workflows.
- Master bot callback buttons can assign requests, change status, request comments, and open request cards.
- Integration bot supports `/start`, `/events`, `/failed`, `/pending`, `/stats`, `/event <id>`, `/retry <id>`, and `/ignore <id>`.
- WebApp submissions can duplicate new requests into a Telegram masters chat when `TELEGRAM_MASTER_BOT_TOKEN` and `TELEGRAM_MASTERS_CHAT_ID` are configured.

### Confirmed by tests
- Telegram client, master, integration, reporting, feedback, and keyboard flows are covered by the Node test suite.

### Confirmed only partially / runtime-dependent
- Outbound Telegram delivery logic is implemented, but real delivery depends on valid tokens, webhook setup, and network reachability.
- Telegram WebApp identity values are read from Telegram runtime objects, but cryptographic verification is not implemented in this repo.

### Session-specific / non-global observations
- A mini-app issue observed in an old or cached user session would be a session-specific runtime observation unless reproduced broadly; the codebase alone does not justify describing it as a global Telegram production blocker.

## What changed after modernization
- Telegram flows are now explicitly part of the active Node-first runtime rather than a historical or parallel contour.
- Master-bot request management, comments, assignments, and reporting are implemented against the shared SQLite-backed core.
- Client-bot WebApp launching and 10-digit phone normalization are synchronized with the current WebApp/server logic.
- Integration-bot operations are now documented as Telegram-only, which removes ambiguity about channel support.

## Remaining gaps
- No automatic Telegram webhook registration exists in the repository.
- No app-level Telegram webhook secret validation is present.
- Bot sessions remain in memory and disappear on restart.
- The integration bot relies on possession of the Telegram bot/token rather than a richer operator auth model.

## Risks
- Missing Telegram tokens do not always fail startup, so some flows can appear alive while outbound responses silently fail or are skipped.
- WebApp identity and chat-origin identity still rely on provider payload trust rather than stronger verification.
- Master/admin access depends on correct env bootstrap and DB staff state.
- Telegram-specific client sessions can become stale after restarts because conversational session state is not persisted.

## Legacy / dead / misleading parts
- Historical Python Telegram bot code is not part of the active production runtime.
- Any repository narrative that frames Telegram as legacy-only is now misleading.
- Integration bot support should not be described as multi-channel; in current code it is Telegram-only.

## Confidence level
High for code-confirmed Telegram functionality; medium for live platform registration/delivery because no production webhook inspection was performed.

## Recommended follow-up checks
- Verify all three Telegram webhooks are registered in production.
- Smoke-test `/start`, a quick request, a master status change, and one integration-bot command with live credentials.
- Confirm masters-chat duplication works in the live environment when configured.

---

## TESTING_AUDIT.md
<a id="testing-audit"></a>

### Preserved content

# Testing Audit

## Scope
Current automated test inventory, what is covered by unit/integration-style tests, what still relies on manual QA, and which critical scenarios remain under-verified.

## Current state
- The active automated suite is `npm test`, which runs Node's built-in test runner over `tests/node/**`.
- Legacy Python tests still exist but do not represent the active production contour.
- Test coverage is strongest around config, server routes, SQLite persistence, request lifecycle, Telegram/MAX handlers, reporting, and WebApp phone behavior.

## Confirmed facts
### Automated tests that really exist
- Config/env parsing tests.
- Production-path and repo-structure checks.
- Health endpoint tests.
- SQLite initialization, migration, restart-survival, and persistence tests.
- WebApp phone-input and form-submission tests using JSDOM.
- Telegram client bot, master bot, and integration bot tests.
- MAX channel and hardening tests.
- Status model, request-event, analytics/reporting, integration-flow, and operational-flow tests.

### Unit-style / focused component coverage
- Phone normalization and request validation helpers.
- Config parsing and env sanitization.
- Channel adapter parsing.
- Some DB operations and validation helpers through focused Node tests.

### Integration-style / runtime-path coverage
- HTTP server route behavior, including health, request creation, internal routes, reports, and integration endpoints.
- SQLite persistence across restart.
- WebApp-to-server submit flow in simulated environments.
- Bot webhook handling across Telegram and MAX.
- Scheduler claiming/recovery behavior.

### Manual-QA-only or runtime-only areas
- Real Telegram outbound message delivery.
- Real MAX outbound message delivery.
- Real Telegram WebView behavior on actual devices.
- Real MAX WebView behavior on actual devices.
- Real BotHost persistence path survival across an actual deploy/redeploy.
- Real webhook registration state in Telegram and MAX control planes.

### Critical scenarios explicitly represented
- Phone validation and normalization.
- DB/persistence init, migration, CRUD, and restart survival.
- Status model and request-event generation.
- Analytics event creation and reporting behavior.
- Export and diagnostics/health endpoints.

## What changed after modernization
- The test story is now centered on the Node runtime, not on historical Python contours.
- SQLite persistence and migration behavior are now directly covered.
- Phone-input behavior after the recent fixes is specifically covered in JSDOM tests.
- MAX behavior is no longer undocumented or purely aspirational; it has automated regression coverage, albeit not live-platform proof.

## Remaining gaps
- No live end-to-end post-deploy smoke suite is stored in the repo.
- No browser-container screenshot or visual regression artifact was captured in this environment.
- No authenticated/perimeter production security tests are present.
- Legacy Python tests remain as historical residue and can confuse readers about the active validation strategy.

## Risks
- Passing `npm test` does not prove Telegram/MAX credentials, webhook registration, or external API reachability.
- Simulated webview tests cannot guarantee all device/browser/runtime quirks are resolved.
- If legacy Python files remain, contributors may misread skipped Python tests as meaningful runtime coverage.

## Legacy / dead / misleading parts
- Python tests are historical, not authoritative production validation.
- Any old testing narrative that describes Python tests as a primary gate is stale.
- Test presence should not be confused with live deploy verification.

## Confidence level
High for code-level regression coverage; medium for real deployed behavior because runtime/provider verification still has to be done manually.

## Recommended follow-up checks
- Keep `npm test` as the minimum regression gate.
- Add a documented live post-deploy smoke record for Telegram, MAX, WebApp submit, and persistence restart checks.
- If the Python contour is truly retired, consider archiving or clearly labeling the skipped Python tests.

---

## WEBAPP_AUDIT.md
<a id="webapp-audit"></a>

### Preserved content

# WebApp Audit

## Scope
Current WebApp routes, forms, submit logic, validation, identity handling, phone-input behavior, and UX/runtime caveats for Telegram and MAX.

## Current state
- The WebApp shell is `public/index.html`, but behavior is defined by `public/webapp.js` and runtime values injected by the server.
- The server serves the same HTML shell for `/`, `/requests`, `/recommendations`, and five form routes.
- Active forms are: service request, parts request, consultation request, warranty request, and data-change request.
- The phone field now stores digits-only raw values with a hard 10-digit cap in the visible input.

## Confirmed facts
### Confirmed by code
- Form routes map to API endpoints under `/api/client/requests/service|parts|consultation|warranty|data-change`.
- Client-side required-field validation is per request type and mirrors server-side field expectations.
- The phone input controller strips non-digits, limits input to 10 digits, normalizes pasted values, and blocks submit when invalid.
- Submit logic normalizes `payload.phone`, optionally replaces it with `nativeContactState.phoneNumber`, attaches channel identity, and posts JSON to the relevant request endpoint.
- Channel detection uses the `channel` query parameter first; if `channel=max`, the WebApp treats the source as MAX.
- Telegram identity is read from `window.Telegram.WebApp.initDataUnsafe.user.id` or cached localStorage fallback.
- MAX identity is read from `window.MAX.WebApp.initDataUnsafe.user.id` or cached localStorage fallback.
- Native contact acquisition prefers `MAX.WebApp.requestContact()` when available, otherwise `Telegram.WebApp.requestContact()` when available.
- Result screens include Telegram channel CTA buttons using the injected `TELEGRAM_CHANNEL_URL` / legacy alias.
- `/requests` requires a 10-digit phone input and fetches `GET /api/client/requests?phone=...`.
- `/recommendations` exists as a route in the shell, but effective data depends on server-side recommendation availability and Telegram-ID based lookup.

### Confirmed by tests
- JSDOM tests cover phone normalization, paste/edit behavior, invalid-submit blocking, and submission payloads for both Telegram and MAX-simulated webviews.

### Confirmed only partially / not cryptographically confirmed
- Telegram and MAX identity handling is code-confirmed, but the repository does not cryptographically verify WebApp identity or init data.
- Native-contact behavior is implemented, but real provider runtime behavior still depends on actual Telegram/MAX webview support.

### Hypothesis only
- Any claim that all device-specific WebView quirks are fully eliminated would be too strong without live runtime checks.

## What changed after modernization
- Phone input behavior is now explicitly digits-only and 10-digit constrained instead of relying on looser or mask-driven assumptions.
- WebApp payload preparation now consistently carries `sourceChannel`, `telegramId`, or `maxId` depending on context.
- Runtime config injection allows a single shell to serve Telegram and MAX contexts without editing `public/index.html`.
- Previous generic claims about WebApp instability are no longer accurate as blanket statements; the code and tests show concrete improvements.

## Remaining gaps
- There is no cryptographic verification of Telegram/MAX WebApp identity.
- Field definitions and validation rules still exist in both client and server code, so drift remains possible.
- No offline retry/queue UX exists for failed submits.
- Recommendation retrieval currently relies on Telegram ID, so MAX-specific recommendation parity remains limited in the server API surface.

## Risks
- Cached localStorage identity can preserve old user/channel identifiers inside a stale client session.
- Trust in `initDataUnsafe` and client-provided IDs creates spoofing risk for workflows that assume strong identity.
- UX still depends on provider support for `requestContact()` and mini-app launch behavior.
- Recommendations can appear empty in legitimate production scenarios when sync data is absent; this is a remaining runtime/data dependency, not proof of a frontend bug.

## Legacy / dead / misleading parts
- `src/interfaces/webapp/routes.js` and `src/interfaces/webapp/state.js` are not the runtime route or state source of truth for the shipped WebApp.
- Older audit claims that described the phone field as fundamentally broken should not be retained as current production facts.
- `review.html` is outside this audit rewrite scope and was intentionally not changed.

## Confidence level
High for code-confirmed WebApp behavior and phone handling; medium for real-device Telegram/MAX runtime behavior because no live device validation happened in this pass.

## Recommended follow-up checks
- Run live Telegram WebApp tests for all five forms, including native contact fill and result screen links.
- Run live MAX WebApp tests for launch, identity propagation, and contact access.
- Check whether stale-client-session behavior reproduces only on specific sessions/devices before treating it as a global production issue.

---

