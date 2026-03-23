# MASTER_AUDIT

`audit/MASTER_AUDIT.md` is the single source of truth for repository audit information.
Do not recreate split audit files.

## Architecture
- Node-first runtime rooted at `app.js` and `src/server/index.js`.
- Shared server hosts WebApp, Telegram webhooks, MAX webhooks, internal admin routes, and scheduler bootstrap.
- MAX remains embedded in the same project; no separate BotHost service.
- AI layer exists only as disabled infrastructure in `src/infrastructure/ai/`.

## Runtime
- Single-process Node runtime.
- Master-bot menu is inline callback-based with stable `menu:*` callback ids.
- Request-card actions are handled in `src/interfaces/master_bot/index.js` and validated through centralized transition rules.

## Env
- Core env is loaded in `src/infrastructure/config/index.js`.
- AI env is present but disabled by default.
- Diagnostics mask secrets and expose readiness only.

## Persistence
- SQLite is canonical.
- Requests store lifecycle fields for assignment, archive, follow-up, completion, outbound errors, and rejection reason.
- `request_events` is the operational audit trail.
- `tasks` persists scheduler work for feedback and follow-up.

## WebApp
- Production shell stays in `public/index.html` and `public/webapp.js`.
- Phone rule remains 10 digits without `+7/8`.
- `review.html` and `public/index.html` are outside this modernization scope for direct edits.

## Telegram
- Telegram client, master, and integration bots remain supported.
- Integration bot is still Telegram-only.
- Telegram source requests route clarification back to Telegram first.

## MAX
- MAX client/master webhooks remain in the same runtime.
- MAX source requests route clarification back to MAX first.
- Fallback to Telegram is allowed only when a real Telegram identity exists.

## Security
- Admin bootstrap is env-driven.
- Persistent role grants/revocations happen through bot access flow.
- Diagnostics/logs are admin-only.
- Secrets are masked in diagnostics.
- Email is not used as an outbound clarification channel.

## Testing
- Node test suite covers state transitions, follow-up scheduler behavior, routing, diagnostics/logging, and regression flows.
- Post-deploy smoke should explicitly exercise both Telegram and MAX master menus plus legacy callbacks.

## Deploy risks
- SQLite file permissions and persistence mount quality remain critical.
- Real provider delivery still depends on valid bot tokens and network reachability.
- Live MAX subscription health should still be verified after deployment.

## External AI starter notes
- AI is infrastructure-only right now.
- Runtime request handling does not invoke AI providers.
- Before enabling AI in production, add provider-specific rate limiting, audit logging, and user-facing fallback messaging.
