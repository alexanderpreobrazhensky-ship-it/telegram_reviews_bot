# Security Audit

## Scope
Webhook validation, token handling, header validation, spoofing surface, unauthenticated routes, identity binding, internal routes, and diagnostics exposure.

## Current state
- MAX webhooks have an explicit shared-secret validation layer.
- Telegram webhooks do not have an equivalent secret/header validation layer in this repository.
- Internal admin pages are gated by env-driven whitelist IDs supplied via header or query param.
- Several integration endpoints are unauthenticated beyond network reachability.

## Confirmed facts
- MAX secret validation exists and rejects disabled/misconfigured/invalid requests with explicit status codes.
- MAX secret headers are sanitized in logs.
- Internal routes `/internal/requests` and `/internal/export` require a whitelisted admin ID.
- `/health`, `/health/db`, and `/health/max` expose diagnostics without authentication.
- `/api/integrations/email`, `/api/integrations/manual`, and `/api/integrations/one-c/*` do not enforce auth middleware in the current server.
- WebApp and client request APIs trust client-provided identity hints (`telegramId`, `maxId`, WebApp init data) without signature verification.

## Risks
- Spoofing risk exists on unauthenticated integration endpoints.
- Internal admin auth is simple shared-ID allowlisting, not session-based or signed.
- Telegram webhook routes rely on path secrecy / provider setup rather than explicit request signing in the app.
- Health diagnostics leak useful config posture such as env audit and MAX readiness flags.

## Gaps
- No authentication middleware for 1C/manual/email endpoints.
- No signed verification for Telegram/MAX WebApp identity.
- No explicit CSRF/session model because the app is primarily webhook/API driven.
- No rate limiting on all sensitive non-webhook API routes.

## Legacy / dead / misleading parts
- `ONE_C_WEBHOOK_SECRET` exists in config but is not enforced today.
- Placeholder env names can make the current security posture look stronger than it is.

## Recommendations
1. Add auth to `/api/integrations/*`, ideally shared-secret or signed requests per source.
2. Consider Telegram webhook verification or secret-token usage if deployment platform supports it.
3. Reduce diagnostic exposure on health endpoints in stricter production environments.
4. Add signature verification for WebApp identity if business rules start relying on it for privileged actions.

## Confidence level
High for code-confirmed route posture; medium for production perimeter assumptions because reverse-proxy/network controls are outside the repo.

## Follow-up checks
- Verify whether BotHost/proxy already restricts integration routes.
- Audit logs in production for unexpected direct hits to integration and internal endpoints.
