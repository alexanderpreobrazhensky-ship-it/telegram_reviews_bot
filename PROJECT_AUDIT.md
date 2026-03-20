# PROJECT_AUDIT.md

## Production contract

- Runtime: **Node.js-first**. Production bootstrap lives in `app.js`; `package.json.main`, `npm start`, Docker `CMD` and `.bothost/entrypoint.conf` all point to the same entrypoint.
- Install contract: `package-lock.json` exists, and Docker uses `npm ci --omit=dev`, so the repository is aligned with deterministic Node deploys.
- Branch contract for BotHost: `.bothost/entrypoint.conf` pins `branch=main`, while the current working branch in the repo is `work`. This is not a runtime blocker for local analysis, but it is a deploy expectation mismatch that must be remembered on BotHost.
- Port contract: runtime reads `process.env.PORT` with a fallback to `3000`. BotHost should supply `PORT`; local fallback is only safe for local runs.
- Startup contract: the single Node process starts HTTP, then starts the scheduler after `server.listen()` succeeds.

## Entrypoints and startup chain

1. `app.js` calls `loadConfig()`.
2. `app.js` creates the HTTP server via `createServer({ config, logger })`.
3. `createServer()` registers the client, master, and integration bot webhook routes.
4. `app.js` creates one in-process scheduler instance wired to the same file DB.
5. `server.listen(config.port)` starts the HTTP listener.
6. The scheduler starts only after the listen callback fires.
7. `server.close` stops the scheduler.

### Practical implication

- The project is **single-process** and **single-node by design**.
- HTTP, Telegram/MAX webhook handling, reporting, integrations, and scheduled jobs all share the same event loop and the same file DB.
- There is no separate worker startup chain despite several legacy/declarative ENV names implying one.

## Runtime model

### Active runtime

- `app.js` is the only production entrypoint.
- `src/server/index.js` is the runtime router and static file server.
- `src/infrastructure/config/index.js` is the only active Node config loader.
- `src/infrastructure/db/index.js` is the active persistence layer.
- `src/infrastructure/scheduler/index.js` is the active scheduler.
- `src/interfaces/client_bot`, `src/interfaces/master_bot`, and `src/interfaces/integration_bot` are the active bot adapters.

### Inactive or non-production contours

- `bots/**`, `services/**`, `shared/**`, and `requirements.txt` form a large legacy Python contour.
- `legacy/index.js` is just a shim and is not part of the active deploy path.
- `src/interfaces/webapp/state.js` and `src/interfaces/webapp/routes.js` are present, but the server router is implemented directly in `src/server/index.js`.

### Operating assumptions

- Only one process should write to the JSON DB at a time.
- File storage must survive redeploys, otherwise requests, staff access, report snapshots, scheduled tasks, and feedback history will be lost.
- Scheduler correctness assumes one scheduler instance against one DB file.

## Repository snapshot

### Production-critical files

- `app.js`
- `package.json`
- `package-lock.json`
- `Dockerfile`
- `.bothost/entrypoint.conf`
- `src/server/index.js`
- `src/infrastructure/config/index.js`
- `src/infrastructure/db/index.js`
- `src/infrastructure/scheduler/index.js`
- `src/interfaces/client_bot/index.js`
- `src/interfaces/master_bot/index.js`
- `src/interfaces/integration_bot/index.js`
- `src/infrastructure/messaging/index.js`
- `public/index.html`, `public/webapp.js`, `public/styles.css`

### Supporting but non-critical files

- `logo.png`
- `tests/node/**`
- `README.md`
- `DEPLOY_ENV_REFERENCE.md`

### Legacy / historical tails

- `bots/client_bot/**`
- `services/client_bot_service/**`
- `shared/**`
- Python requirements and tests

These files still read many ENV variables, but they are **not** part of the Node production path. They matter for audit completeness and future cleanup, not for the current BotHost runtime.

## Route inventory

### Health and static/webapp routes

- `GET /health`
- `GET /styles.css`
- `GET /webapp.js`
- `GET /logo.png`
- `GET /`
- `GET /requests`
- `GET /recommendations`
- `GET /forms/service-request`
- `GET /forms/parts-request`
- `GET /forms/consultation`
- `GET /forms/warranty-request`
- `GET /forms/data-change-request`

### Client API

- `POST /api/client/requests/service`
- `POST /api/client/requests/parts`
- `POST /api/client/requests/consultation`
- `POST /api/client/requests/warranty`
- `POST /api/client/requests/data-change`
- `GET /api/client/requests`
- `GET /api/client/recommendations`
- `POST /api/client/recommendations/:id/interest`

### Telegram and MAX webhook routes already implemented

- `POST /telegram/client_bot/webhook`
- `POST /telegram/master_bot/webhook`
- `POST /telegram/integration_bot/webhook`
- `POST /max/client_bot/webhook`
- `POST /max/master_bot/webhook`

### Integration API

- `POST /api/integrations/email`
- `POST /api/integrations/manual`
- `POST /api/integrations/one-c/client`
- `POST /api/integrations/one-c/vehicle`
- `POST /api/integrations/one-c/visit`
- `POST /api/integrations/one-c/recommendation`
- `GET /api/integrations/events`
- `GET /api/integrations/events/:id`
- `POST /api/integrations/events/:id/retry`

### Reporting API

- `GET /api/reports/summary`
- `GET /api/reports/requests`
- `GET /api/reports/feedback`
- `GET /api/reports/quality`
- `GET /api/reports/masters`
- `GET /api/reports/sources`
- `GET /api/reports/recommendations`
- `POST /api/reports/snapshots`
- `GET /api/reports/snapshots`
- `GET /api/reports/snapshots/:id`

### MAX route readiness conclusion

- The repository already has two MAX webhook routes and MAX-aware client/master adapters.
- There is **no MAX integration bot route**.
- There is **no MAX-specific recommendation auth route**: `/api/client/recommendations` still authenticates only via `telegramId`.
- Logical expansion points for new MAX routes are already clear:
  - `/max/integration_bot/webhook` if an operator bot is needed in MAX.
  - MAX-aware recommendation/auth endpoints under `/api/client/*`.
  - Additional MAX callback/deep-link routes can stay inside existing adapter modules.

## Bot audit

### Telegram client bot

Implemented and active:

- `/start` opens the shared WebApp and supports quick flows.
- Chat-based quick request capture stores clients, requests, and communication events.
- Rating messages `1..5 [comment]` are parsed into feedback and can trigger quality cases.
- Scheduler can send outbound feedback requests through the client bot token.

Weak spots:

- Chat sessions are stored in an in-memory `Map`, so all partially collected requests are lost on restart.
- Telegram delivery failures are swallowed with `catch(() => {})`, so delivery can silently fail.
- Quick flow phone validation is weaker than WebApp validation.

### Telegram master bot

Implemented and active:

- Access control via file DB roles plus env bootstrap admins.
- Request lists, search, cards, status changes, comments, notes, report commands, and quality-case commands.
- Clarification messages can be sent back to the client through the same channel the client used.

Weak spots:

- Access control is file-DB based and local to this instance.
- Role bootstrap depends on correct `MASTER_BOT_ADMIN_IDS` / `MAX_MASTER_BOT_ADMIN_IDS` setup.
- Masters-chat notifications exist only for Telegram; there is no MAX masters group/channel fan-out equivalent.

### Integration bot

Implemented and active:

- Telegram-only operator bot for integration events.
- Can inspect, retry, and ignore integration events.

Weak spots:

- No separate worker isolation.
- No route-level auth beyond Telegram bot possession.
- No MAX integration bot contour yet.

## WebApp audit

### Current state

- Shared WebApp is served from `public/index.html` plus `public/webapp.js`.
- Runtime HTML injection adds `WEBAPP_TELEGRAM_CHANNEL_LINK`, `WEBAPP_URL`, `MAX_WEBAPP_URL`, `MAX_BOT_NAME`, and `MAX_DEEPLINK_BASE_URL` metadata.
- The frontend already detects `channel=max` and can submit requests as `sourceChannel = max_webapp` with `maxId`.
- A single WebApp can therefore already serve both Telegram and MAX request forms.

### Important limitations

- Recommendations remain Telegram-authenticated only; MAX recommendation UX is intentionally left inactive in the frontend.
- No dedicated MAX theming, auth, or session-verification layer exists yet.
- Shared WebApp reuse is viable, but auth and identity abstractions are incomplete for parity.

### Conclusion on shared WebApp reuse

- **Yes, a unified WebApp is feasible** for the request-creation contour.
- **No, the shared WebApp is not yet feature-complete for all MAX scenarios**, especially recommendations and richer platform-specific auth.

## Persistence audit

### Where the database lives

- Active persistence is a JSON file at `process.env.DB_FILE_PATH` or fallback `data/db.json`.
- The DB module resolves the path at module load time and performs synchronous file reads/writes.

### Behavior on empty or corrupted DB

- If the DB file is missing, `ensureStore()` creates a fresh initial store.
- If the DB file exists but parsing fails, `safeReadStoreRaw()` falls back to a fresh initial store in memory.
- On the next write, that fresh structure can overwrite the broken DB state.

### Risks

- A corrupted JSON DB can effectively lead to silent logical reset.
- There is no backup, WAL, journaling, or schema migration safety net.
- Atomic writes use `temp + rename`, which is good, but there is no cross-process locking.
- If BotHost redeploys into ephemeral storage and `DB_FILE_PATH` is not mounted to persistent storage, requests can disappear.
- Scheduler tasks, access control, and snapshots live in the same DB file, so loss of the DB file means loss of operational continuity, not just history.

### BotHost persistence conclusion

- File DB is acceptable only for **small single-instance deployments with guaranteed persistent volume semantics**.
- It is a real risk area for a growing multi-channel platform.

## Scheduler/task audit

### Implemented

- One in-process scheduler loop.
- Configurable interval, batch size, max attempts, and stuck timeout.
- `feedback_request` handler sends outbound messages through Telegram or MAX depending on client preference.

### Weak spots

- Scheduler runs in the same process as HTTP; heavy HTTP load can affect task latency.
- There is no distributed coordination if a second instance appears.
- Handler set is mostly placeholders besides `feedback_request`.
- Retry knobs for integration events exist in config, but there is no separate retry worker using them.

## Integration layer audit

### Active behavior

- Email ingestion works and creates requests in the same DB.
- Manual import works and is processed through the same integration event flow.
- 1C routes currently accept payloads and normalize them into a partial skeleton.
- Recommendation sync is the most complete 1C branch; client/vehicle/visit sync remain skeletal and often end as ignored/normalized placeholders.

### Drift / dead declarations

The following ENV are read by config but do not materially gate the active HTTP behavior:

- `ONE_C_WEBHOOK_SECRET`
- `ENABLE_INTEGRATION_WORKER`
- `ONE_C_SYNC_ENABLED`
- `EMAIL_IMPORT_ENABLED`
- `INTEGRATION_RETRY_MAX`
- `INTEGRATION_RETRY_DELAY_SECONDS`
- `DB_URL`
- `QUEUE_DRIVER`

That means documentation can easily overstate integration maturity.

## Reporting audit

### Implemented

- Management summary, request metrics, feedback metrics, quality metrics, master metrics, source metrics, recommendation metrics.
- Report snapshots are persisted in the same file DB.
- Role checks for report commands are present in the master bot layer.

### Limitations

- Reporting fidelity depends entirely on the consistency of the same JSON store.
- Missing visits and partial 1C sync limit the realism of funnel metrics.
- There is no external BI/export pipeline.

## Tests audit

### What is covered

- Config defaults and env sanitization.
- Production-path checks.
- Health/static routes.
- Client request flows.
- Master bot flows.
- Integration flows.
- Reporting routes and snapshots.
- Scheduler retry/recovery basics.
- MAX client and master bot foundations.

### What is explicitly legacy

- Python tests under `tests/test_*.py` are skipped or scoped out of the Node-first story.

### What is not covered enough

- BotHost-specific deploy smoke on persistent storage.
- DB corruption and recovery safety.
- Restart behavior for in-memory sessions.
- Real webhook secret validation for 1C because the secret is not wired.
- MAX recommendation auth and parity flows.
- Dual-channel regression with Telegram + MAX active together after repeated deploys.

## Documentation audit

### Aligned documents

- `package.json`, Dockerfile, `.bothost/entrypoint.conf`, and `app.js` agree on the Node entrypoint.
- README route inventory broadly matches the server router.

### Drift found

- README still groups several integration-related ENV as optional runtime knobs even though some of them are effectively declarative/dead in the current Node path.
- `.bothost/entrypoint.conf` expects branch `main`, while current local work is on branch `work`.
- Legacy Python contour still contains a very large ENV surface that could confuse operators if they rely on repository-wide grep without understanding runtime scope.

## Deploy readiness audit

### What is required for a normal deploy

At minimum for a realistic working deploy:

- BotHost/host-provided `PORT`
- `TELEGRAM_CLIENT_BOT_TOKEN`
- `TELEGRAM_MASTER_BOT_TOKEN`
- `MASTER_BOT_ADMIN_IDS`
- `WEBAPP_URL`
- `DB_FILE_PATH` pointing to persistent storage

For the full currently implemented Telegram contour:

- `TELEGRAM_INTEGRATION_BOT_TOKEN`
- optionally `TELEGRAM_MASTERS_CHAT_ID`
- optionally `WEBAPP_TELEGRAM_CHANNEL_LINK` or alias `TELEGRAM_CHANNEL_URL`
- scheduler tuning envs if non-default behavior is needed

### Main deploy blockers

- Persistent storage is the main operational dependency.
- If persistent storage is not guaranteed on BotHost, the current architecture is not robust enough for business-critical multi-channel growth.
- Silent DB reset risk on corrupted JSON remains a real weakness.

## BotHost-specific audit

### Is it safe to keep expanding this project on BotHost?

**Short answer: conditionally, but not comfortably.**

Safe enough only if all of the following stay true:

- one instance only;
- persistent volume for `DB_FILE_PATH` is guaranteed across redeploys;
- webhook URLs stay stable;
- deploy smoke checks are done after every release.

### What is already risky

- File DB as the single system of record.
- Scheduler and HTTP sharing one process.
- No cross-instance locking.
- Silent delivery failures to Telegram/MAX APIs.
- Large legacy contour creating config confusion.

### What is a real blocker

- Lack of guaranteed persistent storage for `DB_FILE_PATH` is the clearest real blocker.
- If BotHost cannot guarantee stable persisted storage semantics, further functional growth is unsafe.
- If BotHost starts more than one instance, scheduler/task correctness becomes unsafe.

### Can new ENV and webhook routes still be added?

- **Yes, structurally the code can absorb more ENV and more routes.**
- The route registration pattern is simple and extensible.
- The config loader can accept more variables easily.
- The real constraint is not code shape; it is operational fragility of the single-process + file-DB model.

### What must be checked after every BotHost deploy

1. `GET /health` returns 200.
2. Static routes and WebApp routes respond.
3. Telegram webhook endpoints still answer 200/expected app-level response.
4. MAX webhook endpoints still answer 200/expected app-level response.
5. `DB_FILE_PATH` still points to the same persistent file and historical data is intact.
6. New request creation works from WebApp.
7. Master bot access still recognizes bootstrap admins.
8. Scheduled tasks remain present after redeploy if they existed before.

## Full ENV audit

The complete per-variable reference is maintained in **`DEPLOY_ENV_REFERENCE.md`**.

### Summary by status

- **required**: `PORT` (platform contract), plus a practical production minimum of `TELEGRAM_CLIENT_BOT_TOKEN`, `TELEGRAM_MASTER_BOT_TOKEN`, `MASTER_BOT_ADMIN_IDS`, `WEBAPP_URL`, `DB_FILE_PATH`.
- **recommended**: `TELEGRAM_INTEGRATION_BOT_TOKEN`, `TELEGRAM_MASTERS_CHAT_ID`, `WEBAPP_TELEGRAM_CHANNEL_LINK`, MAX-specific envs when MAX is enabled.
- **optional**: scheduler tuning, `NODE_ENV`, `MAX_DEEPLINK_BASE_URL`, `WEBAPP_DEDUPE_WINDOW_MS`.
- **legacy/dead/documented-only**: the config-only integration worker/queue/SQL toggles and the large Python-only env surface.

## MAX readiness audit

### What is already ready

- Separate MAX webhook routes for client and master bot already exist.
- Shared channel-adapter abstractions already normalize Telegram and MAX events.
- Messaging layer already supports MAX send-message and callback-answer APIs.
- DB schema already has `maxId`, `preferredChannel`, and MAX-aware source channels such as `max_chat` and `max_webapp`.
- Master-to-client outbound routing already chooses Telegram vs MAX based on the stored preferred channel.
- Shared WebApp already supports request creation from `channel=max`.

### What is not ready yet

- No MAX integration bot route.
- No MAX equivalent of Telegram masters chat duplication.
- Recommendations are still Telegram-only for auth and fetch flow.
- `MAX_ENABLED` is read but does not actually gate route wiring.
- `MAX_DEEPLINK_BASE_URL` is injected as metadata only; it is not a primary deep-link builder input.
- Operational tests do not yet cover full Telegram + MAX coexistence under repeated restart/redeploy conditions.

### Can a MAX client/master bot be added without breaking Telegram?

- **Yes, the current architecture is reasonably extendable for MAX client/master bot expansion.**
- Telegram and MAX already share adapter patterns while still using channel-specific tokens and secrets.
- The safest path is additive: keep Telegram routes unchanged, add MAX-only envs and feature-specific tests, and preserve shared domain storage.

### Which ENV will be needed for MAX

At minimum for a real MAX contour:

- `MAX_CLIENT_BOT_TOKEN`
- `MAX_MASTER_BOT_TOKEN`
- `MAX_MASTER_BOT_ADMIN_IDS`
- `MAX_WEBHOOK_SECRET`
- `MAX_BOT_NAME`

Usually also recommended:

- `MAX_WEBAPP_URL` if MAX should use a distinct Mini App URL
- `MAX_DEEPLINK_BASE_URL` if a separate deep-link base is needed
- `MAX_ENABLED` as an operator-facing flag, even though it is not yet a hard runtime gate

### Which routes will be needed or extended

- Keep using existing `POST /max/client_bot/webhook` and `POST /max/master_bot/webhook`.
- Likely add `POST /max/integration_bot/webhook` if operator workflows are needed in MAX.
- Extend `/api/client/recommendations` to support MAX identity, not only Telegram identity.
- Optionally add MAX-specific report or staff-notification fan-out if Telegram masters chat duplication is no longer sufficient.

### MAX over BotHost risk summary

- Architecturally feasible.
- Operationally fragile if BotHost storage/process guarantees are weak.
- The biggest risk is not the MAX adapter code; it is the platform model underneath the shared file DB and scheduler.

## Risks and limitations

1. JSON file DB is the single biggest operational risk.
2. Corrupted DB can lead to implicit reset behavior.
3. Single-process scheduler + HTTP runtime does not scale safely to multi-instance.
4. Delivery failures to Telegram/MAX APIs are mostly swallowed.
5. In-memory conversational sessions are restart-fragile.
6. Large legacy Python contour creates documentation and ENV drift risk.
7. Several documented integration envs do not materially affect runtime.
8. MAX support is foundation-level, not end-to-end parity.

## Final deploy conclusion

- **Telegram-only MVP on BotHost:** viable if persistent storage is configured and post-deploy smoke checks are disciplined.
- **Growing multi-bot, multi-channel production platform on BotHost:** increasingly risky with the current file-DB + single-process design.
- **MAX expansion:** technically possible without breaking Telegram, because the channel-adapter foundation is already present.
- **Main recommendation before serious expansion:** keep the current code shape, but treat persistence guarantees, restart safety, and post-deploy checks as mandatory operational controls.

## Protected file verification note

- This audit intentionally leaves `review.html` unchanged.
- This audit intentionally leaves all existing `index.html` files unchanged, including `public/index.html` and `bots/client_bot/webapp/index.html`.
- Final verification is performed before completion via file existence and hash comparison.
