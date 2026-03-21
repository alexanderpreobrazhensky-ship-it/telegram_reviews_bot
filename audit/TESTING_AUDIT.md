# Testing Audit

## Scope
Automated test inventory, executed checks, manual QA coverage status, regression scope, and remaining verification gaps.

## Current state
- Primary automated suite is Node’s built-in test runner over `tests/node/**`.
- Legacy Python tests exist but are all skipped.
- This audit run restored missing Node dependency installation, then executed the full Node suite successfully.

## Confirmed facts
### Automated checks executed in this audit
- `npm install` succeeded and restored `better-sqlite3`.
- `npm test` passed: 60/60 Node tests.
- `python -m pytest -q tests/test_entrypoints.py tests/test_health.py tests/test_runtime_behavior.py tests/test_static_routes.py tests/test_webhook_url_build.py` completed with 5 skipped tests.

### Code-level coverage areas confirmed by the Node suite
- Config loading and sanitization
- Production-path and structure checks
- Health endpoints
- SQLite initialization, migration, persistence, and restart behavior
- Client request creation for all form types
- Phone normalization and WebApp input behavior
- Telegram client/master/integration flows
- MAX webhook validation and basic flows
- Reporting, analytics, export, dedupe, status transitions, quality cases, scheduler behavior

## Manual QA audit status
### Simulated/manual-equivalent coverage completed
- WebApp phone input behavior via JSDOM
- Request submission flows for Telegram and MAX-simulated webviews
- Telegram and MAX webhook route behavior through automated HTTP tests
- Persistence restart behavior through SQLite tests

### Remaining live manual QA
- Real Telegram WebView device checks
- Real MAX WebView device checks
- Real Telegram/MAX outbound delivery with live credentials
- Real BotHost persistence validation across redeploy

## Risks
- Python tests do not validate a live Python contour because they are intentionally skipped.
- Automated tests cannot prove real external API delivery to Telegram/MAX.
- Browser-container screenshots were not available in this environment, so no visual artifact was captured.

## Gaps
- No full end-to-end deploy smoke against a live BotHost environment.
- No real secret/credential validation in CI from this repository alone.

## Legacy / dead / misleading parts
- Python tests are historical and should not be interpreted as active production validation.

## Recommendations
1. Keep `npm test` as the minimum regression gate.
2. Add a post-deploy live smoke checklist execution record per release.
3. If the Python contour is not coming back, retire or archive the skipped Python tests.

## Confidence level
High for code-level regression, medium for live-provider behavior.

## Follow-up checks
- Run live Telegram/MAX smoke after deploy.
- Validate restart persistence on the real BotHost mount path.
