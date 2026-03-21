# MAX Audit

## Scope
MAX route registration, secret validation, payload handling, identity path, outbound flow, security posture, and production-readiness level.

## Current state
- MAX client route: `/max/client_bot/webhook`.
- MAX master route: `/max/master_bot/webhook`.
- MAX uses the same core services as Telegram where possible, but remains a partial-production contour.

## Confirmed facts
### Confirmed
- MAX routes are registered in the same server as Telegram routes.
- `validateMaxWebhookRequest()` enforces:
  - `MAX_ENABLED`
  - presence of the relevant MAX bot token
  - presence of `MAX_WEBHOOK_SECRET`
  - exact `X-Max-Bot-Api-Secret` header match
  - object-shaped payload
- Headers are sanitized in logs so secrets are not fully dumped.
- MAX client and master flows share the same business logic style as Telegram.
- MAX mini-app links are generated from `MAX_WEBAPP_URL`, `MAX_BOT_NAME`, and optional deep-link metadata.

### Partially confirmed
- Identity is derived from MAX webhook/user payloads and WebApp runtime objects; this is code-confirmed but not cryptographically proven in this repo.
- Outbound flow is implemented against `https://platform-api.max.ru`, but live delivery still depends on real credentials and network.

### Not confirmed
- Real production webhook registration state in MAX control plane.
- Real device-specific MAX WebView quirks beyond automated Node tests.

### Hypothesis only
- Any claim that MAX is fully production-ready would be overstated. The code is foundation-plus-MVP, not a fully hardened contour.

## Risks
- Trust in MAX identity is still based on provided webhook/runtime payloads.
- No MAX integration bot exists.
- There is no separate MAX staff broadcast/fan-out equivalent to Telegram masters chat.
- MAX route presence plus misconfiguration can create confusing operator expectations unless env is documented clearly.

## Gaps
- No signature verification beyond shared-secret header checking.
- No distinct MAX analytics/reporting dashboard beyond shared APIs.
- No explicit MAX-specific fallback when outbound API calls fail, beyond logs and boolean failure.

## Legacy / dead / misleading parts
- `MAX_ENABLED` is not a route-registration switch; it is an acceptance gate inside validation.
- MAX is not an independent BotHost project and must remain embedded in the current Node foundation.

## Recommendations
1. Keep MAX embedded inside the current Node runtime, as required.
2. Treat current MAX support as “usable foundation with tests,” not “fully hardened production parity.”
3. Add stronger identity verification if MAX platform tooling supports it later.
4. Re-run live MAX device QA after deploys that touch callback, WebApp, or access logic.

## Confidence level
Medium-high.

## Follow-up checks
- Perform live webhook and WebView smoke tests in MAX.
- Confirm admin bootstrap with a real `MAX_MASTER_BOT_ADMIN_IDS` value in production.
