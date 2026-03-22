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
- Run the live checks listed in `MASTER_AUDIT_FOR_EXTERNAL_AI.md` after deployment.
- Record the results of `/health`, `/health/db`, `/health/max`, one Telegram request, one MAX request, and one restart-persistence check.
- Re-open security review if integration/reporting endpoints are publicly reachable.
