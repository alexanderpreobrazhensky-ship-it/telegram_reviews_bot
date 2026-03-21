# Repository full audit

## Executive summary
The repository's real production contour is **Node-first**, centered on `app.js`, `package.json`, `src/server/index.js`, `public/**`, and the Node bot/infrastructure modules. The repository is deployable as a small single-instance BotHost service, but it is not fully production-hardened for scale. The main risk areas are JSON-file persistence, in-process scheduling, unauthenticated integration HTTP endpoints, incomplete MAX parity, and a large legacy Python tail that previously polluted the documentation contract.

## 1. Production contract audit
### Actual production contract
- **Runtime:** Node.js.
- **Entrypoint:** `app.js`.
- **Deploy install contract:** `npm ci --omit=dev`.
- **Container command:** `node app.js`.
- **BotHost entrypoint:** `.bothost/entrypoint.conf` → `main_file=app.js`, `branch=main`.
- **Port contract:** `PORT` with fallback `3000`.
- **Persistence contract:** JSON file at `DB_FILE_PATH` or `data/db.json`.

### Conclusion
The production contract is internally consistent in code and deploy files, but previous documentation had severe drift and described a Python-first deploy path that no longer matches the repository.

## 2. Entrypoints and startup chain
1. `app.js` loads config.
2. `app.js` creates the HTTP server.
3. The HTTP server registers bot webhook adapters.
4. `app.js` creates one scheduler instance.
5. The server listens on `config.port`.
6. The scheduler starts after listen succeeds.

### Readiness assessment
- **Entrypoint clarity:** high.
- **Operational isolation:** low.
- **Failure-domain isolation:** low.

## 3. Runtime model audit
### Current model
- Monolithic Node process.
- Shared event loop for HTTP, bot webhooks, and scheduler.
- Shared JSON file persistence.
- External delivery through Telegram and MAX HTTP APIs.

### Implications
- Good enough for small BotHost deployment.
- Weak for concurrency, resilience, and scale.
- No worker separation, queue isolation, or robust back-pressure controls.

### Grade
**Partial / MVP-ready, not scale-ready.**

## 4. Repository snapshot audit
### Production-critical files and directories
- `app.js`
- `package.json`, `package-lock.json`
- `.bothost/entrypoint.conf`
- `Dockerfile`
- `public/**`
- `src/server/**`
- `src/core/**`
- `src/infrastructure/**`
- `src/interfaces/client_bot/**`
- `src/interfaces/master_bot/**`
- `src/interfaces/integration_bot/**`
- `src/integrations/**`
- `tests/node/**`

### Legacy / historical tails
- `bots/**`
- `services/**`
- `shared/**`
- `requirements.txt`
- `tests/test_*.py`
- `legacy/index.js`

### Repository quality conclusion
The runtime core is small and coherent, but the repository surface is noisy because legacy Python material remains close to the production contour.

## 5. Route inventory audit
### Active HTTP routes
#### Health and static
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

#### Client routes
- `POST /api/client/requests/service`
- `POST /api/client/requests/parts`
- `POST /api/client/requests/consultation`
- `POST /api/client/requests/warranty`
- `POST /api/client/requests/data-change`
- `GET /api/client/requests`
- `GET /api/client/recommendations`
- `POST /api/client/recommendations/:id/interest`

#### Integration routes
- `POST /api/integrations/email`
- `POST /api/integrations/manual`
- `POST /api/integrations/one-c/client`
- `POST /api/integrations/one-c/vehicle`
- `POST /api/integrations/one-c/visit`
- `POST /api/integrations/one-c/recommendation`
- `GET /api/integrations/events`
- `GET /api/integrations/events/:id`
- `POST /api/integrations/events/:id/retry`

#### Reporting routes
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

#### Bot webhooks
- `POST /telegram/client_bot/webhook`
- `POST /telegram/master_bot/webhook`
- `POST /telegram/integration_bot/webhook`
- `POST /max/client_bot/webhook`
- `POST /max/master_bot/webhook`

### Route-level audit conclusion
The route map is broad for an MVP. The main gap is that integration routes are operationally sensitive yet unauthenticated.

## 6. Bot audit
### Telegram readiness
- **Client bot:** good MVP readiness.
- **Master bot:** good MVP readiness.
- **Integration bot:** usable but narrow.

### MAX readiness
- **Client bot:** implemented.
- **Master bot:** implemented.
- **Integration bot:** missing.
- **Recommendation parity:** incomplete.

### BotHost readiness
- Works for a single deployed Node process.
- Requires careful secret setup and persistent DB path.
- Needs manual webhook registration and post-deploy smoke verification.

## 7. WebApp audit
### Strengths
- Shared request WebApp works across Telegram and MAX contexts.
- Client-side phone mask and required field logic exist.
- Request source tagging differentiates Telegram/MAX web usage.

### Weaknesses
- Recommendation flow is not fully cross-channel.
- Session/auth assurances are light.
- Some route/state modules are non-authoritative scaffolding.

### Readiness
**Request intake is production-usable; broader account-oriented WebApp behavior is partial.**

## 8. Persistence audit
### Actual persistence
The JSON file DB is the sole active persistence implementation.

### Risks
- Single-writer assumption.
- No transactional guarantees beyond temp-file rename.
- Silent fallback behavior on broken JSON is risky.
- Persistence loss on redeploy is catastrophic for operations.

### Readiness
**Low for scale, acceptable for small persistent single-instance BotHost use.**

## 9. Scheduler/task audit
### What exists
- One in-process polling scheduler.
- Claimed due-task processing.
- Feedback request delivery task.
- Placeholder task types for future scenarios.

### Risks
- Not horizontally safe.
- Not isolated from HTTP workload.
- Not feature-complete beyond one real handler.

### Readiness
**Partial.**

## 10. Integration layer audit
### Implemented
- Email ingestion normalization.
- Manual import intake.
- 1C placeholder sync event intake.
- Integration event inspection/retry tooling.

### Critical risks
- No auth layer on integration HTTP endpoints.
- Several env flags imply more worker/queue machinery than the code really has.
- 1C sync is normalization-first, not full sync orchestration.

### Readiness
**Skeleton to partial, with real security blockers before broad exposure.**

## 11. Reporting/analytics audit
### Implemented
- Summary metrics.
- Request metrics.
- Feedback metrics.
- Quality metrics.
- Master metrics.
- Source metrics.
- Recommendation metrics.
- Snapshot persistence.

### Limitations
- Underlying data quality depends entirely on the JSON operational flow.
- Visit analytics remain underdeveloped.
- No long-term analytics warehouse/export path.

### Readiness
**Partial but useful for operational reporting.**

## 12. Tests audit
### Current tests
- Node test suite is the authoritative automated validation layer.
- Python tests are intentionally skipped and historical.

### Assessment
- Core contract coverage exists.
- No live external-channel e2e automation exists.
- Negative-path security testing is limited.

### Readiness
**Good for repository regression, incomplete for deployment assurance.**

## 13. Deploy readiness audit
### Positive signals
- `package-lock.json` present.
- `Dockerfile` aligned with Node runtime.
- BotHost entrypoint aligned with Node runtime.
- `npm test` exists and is wired in CI.

### Blockers / caveats
- Persistent file storage must be configured.
- Integration endpoints need protection.
- Multi-instance deployment is unsafe.
- External webhook registration is manual.
- MAX requires live credential validation.

### Final deploy conclusion
**Deployable for single-instance BotHost MVP/staging and cautious production, but not yet hardened for scale or open-internet integration exposure.**

## 14. Security and operational risk audit
### High risks
1. Unauthenticated integration endpoints.
2. JSON persistence fragility.
3. Single-process scheduler and runtime coupling.

### Medium risks
1. MAX parity gaps.
2. Legacy Python drift confusing maintainers.
3. In-memory chat session loss on restart.

### Low risks
1. Static asset serving simplicity.
2. Small deploy surface for the active Node contour.

## 15. MAX-specific audit
### Implemented
- MAX client and master webhook routes.
- MAX outbound messaging and callback support.
- MAX mini app URL generation.
- MAX staff bootstrap env.

### Missing / partial
- No MAX integration bot route.
- Recommendation API is still Telegram-centric.
- `MAX_ENABLED` is not a hard route gate.
- Real live-platform smoke is still required.

### MAX readiness conclusion
**Partial-to-good MVP readiness, not fully feature-complete.**

## 16. BotHost-specific audit
### Ready
- Single Node main file.
- Simple deployment contract.
- Compatible port handling.
- Compatible file-based persistence if persistent storage exists.

### Risk items to verify after every deploy
- `DB_FILE_PATH` still points to persistent storage.
- Webhooks remain registered and reachable.
- Admin IDs still unlock master access.
- Scheduler still processes delayed feedback tasks.

### BotHost readiness conclusion
**Reasonably ready for a single-instance BotHost deployment with persistent volume discipline.**
