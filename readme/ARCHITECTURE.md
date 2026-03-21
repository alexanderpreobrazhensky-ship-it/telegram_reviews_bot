# Architecture and repository structure

## 1. Architecture assessment
### Overall architecture
The repository is organized around a compact Node.js platform with light layering:
- `src/core/**` contains domain enums and application services.
- `src/infrastructure/**` contains config loading, logging, DB access, messaging, scheduler, and repository helpers.
- `src/interfaces/**` contains channel/webhook adapters.
- `src/server/index.js` acts as the runtime router.
- `public/**` contains the shipped WebApp frontend.

This is a pragmatic, monolithic service architecture. It is understandable and deployable, but it is only partially layered because the HTTP server still depends directly on DB helpers and some business logic shortcuts.

### Production path vs. repository sprawl
The active runtime is narrow, but the repository contains a large dormant Python contour. That creates cognitive overhead and documentation drift risk. The Node production path is clearer than the repository shape suggests.

### Readiness grade
- **Architecture clarity:** medium.
- **Ease of local operation:** medium/high.
- **Ease of scaling:** low.
- **Ease of further feature extension:** medium.

## 2. Entrypoints and startup chain
1. `app.js` loads config, DB, logger, messaging, and scheduler dependencies.
2. `createServer()` in `src/server/index.js` builds the HTTP server.
3. The server registers the client, master, and integration bot route adapters.
4. `server.listen(config.port)` starts the network listener.
5. The scheduler starts after the server is listening.
6. On `close`, the scheduler stops.

### Consequences
- The platform is a single-process runtime model.
- HTTP latency and scheduler throughput share one event loop.
- There is no dedicated queue worker or scheduler worker process.
- Deploying more than one active instance against the same JSON file is unsafe.

## 3. Bot audit
### Client bot
Implemented behaviors:
- `/start` builds Telegram or MAX-specific launch affordances.
- `/help` returns scenario help.
- Quick actions start in-chat request capture.
- Ratings `1..5` with optional text are parsed into feedback.
- Scheduler can send delayed feedback requests.

Operational caveats:
- Session state uses in-memory `Map`; partially completed chats vanish on restart.
- Quick request collection is less structured than WebApp form validation.
- Delivery depends on external Telegram/MAX APIs with logging but without persistent outbound retry queues.

### Master bot
Implemented behaviors:
- Staff resolution through DB + env admin bootstrap.
- Lists/search/cards/status changes.
- Internal comments and client clarification requests.
- Quality-case listing and updates.
- Telegram and MAX channels share the same service logic.

Operational caveats:
- Role administration remains local to the file DB.
- Telegram masters group duplication exists; there is no equivalent MAX group fan-out.
- Unknown users are denied correctly, but bootstrap quality depends on env correctness.

### Integration bot
Implemented behaviors:
- Telegram-only operator bot.
- Can list recent, failed, and pending integration events.
- Can show event cards, retry events, and mark them ignored.

Operational caveats:
- No MAX integration bot exists.
- The operator route depends on Telegram bot possession only.
- There is no separate process isolation from the main server.

## 4. WebApp audit
### Implemented
- Static shell served from `public/index.html` plus `public/webapp.js`.
- Runtime config is injected server-side without mutating the HTML file on disk.
- Five request forms exist and map to dedicated API routes.
- Phone masking and normalization are implemented in frontend JS.
- Telegram and MAX source identity are distinguished.

### Limitations
- Recommendations are Telegram-identity based; MAX recommendation parity is incomplete.
- Authentication is platform-context based rather than cryptographically verified application sessions.
- Route mapping helpers under `src/interfaces/webapp/**` do not drive the live router.

## 5. Persistence audit
### Active persistence model
- JSON store at `DB_FILE_PATH` or `data/db.json`.
- Sync file IO with temp-file rename for writes.
- One store tracks clients, requests, events, tasks, staff access, quality cases, and reports.

### Risks
- Corrupted JSON can result in effective logical reset on the next write cycle.
- There is no locking for multi-process writes.
- There are no schema migrations or backup hooks.
- DB path is resolved at module load time, so deployment conventions must be stable before startup.

### BotHost implications
- Safe only when the path is persistent across redeploys.
- Unsafe for horizontal scaling.
- Suitable as a small deployment bootstrap, not as a long-term high-volume persistence layer.

## 6. Scheduler/task audit
### Implemented tasks
- `feedback_request` is the only materially implemented handler.
- Other task types exist as placeholders.

### Runtime behavior
- Scheduler polls due tasks on an interval.
- It claims and processes tasks from the same DB.
- It can route feedback requests to Telegram or MAX based on client preference.

### Risks
- In-process scheduler means duplicate processing risk if multiple instances run.
- Placeholder handlers may create false expectations in docs or product planning.
- Failed tasks rely on local retry metadata only.

## 7. Integration layer audit
### Present
- Email ingestion normalizes semi-structured payloads.
- Manual import accepts arbitrary payloads into the integration flow.
- 1C endpoints create normalized integration events.
- Integration reporting and retry mechanisms exist in the shared DB.

### Missing / risky
- No auth guard at the HTTP entrypoint for manual/email/1C routes.
- 1C sync is placeholder/normalization-first, not full bidirectional sync.
- `ENABLE_INTEGRATION_WORKER`, `QUEUE_DRIVER`, and `DB_URL` are configuration remnants rather than active worker/database features.

## 8. Reporting and analytics audit
### Implemented
- Summary, request, feedback, quality, master, source, and recommendation metrics.
- Periodic report snapshots stored in the JSON DB.
- Source analytics distinguish `telegram_chat`, `webapp`, `max_chat`, `max_webapp`, `email`, `manual_import`, and `one_c`.

### Limits
- Reports are only as complete as the JSON store data quality.
- Visit analytics are thin because `visits` are not fully populated by the current production contour.
- No external BI/export pipeline exists.

## 9. Tests audit
### Active automated coverage
- Node tests cover config, module structure, routes, production-path assumptions, master/client flows, MAX channel behavior, reporting, and hardening regressions.

### Legacy tests
- Python tests exist but are skipped and no longer validate the active production contour.

### Coverage assessment
- Runtime/documentation contract coverage is reasonable for a skeleton/MVP service.
- No end-to-end live Telegram/MAX smoke automation exists.
- Integration route auth and persistence failure modes are not deeply exercised.

## 10. Security surface and access model
### Strengths
- MAX webhooks can enforce `MAX_WEBHOOK_SECRET`.
- Master-bot access is denied by default unless user is a configured/stored staff identity.
- Sensitive header values are masked in logs.

### Weaknesses
- Telegram webhooks have no signature verification.
- Manual/email/1C HTTP endpoints are unauthenticated in the server router.
- JSON file persistence stores operational data without encryption or role separation.
- The app has no admin HTTP auth layer.

## 11. Repository-structure quality assessment
### What is good
- Production Node runtime is relatively compact.
- `src/core`, `src/interfaces`, and `src/infrastructure` offer a readable mental model.
- Audit and README contours are now centralized.

### What remains messy
- Legacy Python directories are still very large and close to active code.
- Some scaffolding modules are not authoritative for live behavior.
- Root-level historical docs previously obscured the actual deploy contract.

### Suggested next cleanup steps
- Decide whether the Python contour should be archived outside the main repo or retained with stronger naming.
- Move toward a real DB/queue if BotHost growth is expected.
- Add explicit auth/mTLS/HMAC rules for integration endpoints.
