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
