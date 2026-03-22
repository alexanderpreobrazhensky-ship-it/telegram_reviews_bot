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
