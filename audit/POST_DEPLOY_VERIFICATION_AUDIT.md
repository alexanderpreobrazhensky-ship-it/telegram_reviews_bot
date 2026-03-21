# Post-Deploy Verification Audit

## Scope
Consolidated post-deploy verification facts, unresolved production dependencies, and acceptance against the current task requirements.

## Current state
- Repository, runtime, env, persistence, Telegram, MAX, WebApp, security, documentation, and testing audits have been refreshed.
- All audit artifacts now live in `audit/`.
- All operational README artifacts now live in `readme/`.

## Confirmed facts
- Production runtime remains a single Node-first service.
- SQLite is the real persistence layer.
- Telegram client bot, master bot, integration bot, WebApp, and MAX foundation are all exercised by the Node test suite.
- Recommendations are only meaningfully populated after sync data exists; no claim is made that they are production-complete without real 1C-backed sync.
- Admin access remains env/bootstrap driven and bot-access-flow based, not UI-created superusers.
- Phone normalization remains 10 digits without `+7/8`.

## Risks
- Live provider state (BotHost mounts, Telegram webhook registration, MAX registration, real credentials) is outside repository proof.
- Security hardening is incomplete for integration endpoints.
- MAX remains less battle-tested than Telegram.

## Gaps
- No live BotHost smoke evidence is embedded in the repository.
- No real-device screenshot artifact was captured in this environment.

## Legacy / dead / misleading parts
- Legacy Python contour remains present but non-canonical.

## Recommendations
1. Use this audit set plus the readme set as the new GPT-agent source of truth.
2. Execute a live post-deploy smoke pass using real credentials and record the results externally.
3. Prioritize integration-endpoint auth hardening before broader exposure.

## Confidence level
High for repository/code truth; medium for live deployed infrastructure truth.

## Follow-up checks
- After next deploy, verify `/health`, `/health/db`, `/health/max`, Telegram webhooks, MAX webhooks, one request per form, and a restart persistence check.
