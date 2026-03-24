# Runtime

## Startup chain
1. `app.js` loads config.
2. SQLite store is initialized/migrated.
3. `createServer()` registers routes and bot handlers.
4. Scheduler is created.
5. HTTP server starts listening.
6. Scheduler loop starts after listen.

## Runtime model
- Single Node.js process.
- `http.createServer`, no Express.
- Shared event loop for WebApp, webhooks, scheduler, and internal admin routes.
- Persisted follow-up logic uses SQLite `tasks`, not in-memory timers only.

## Important runtime components
- Master-bot menu router in `src/interfaces/master_bot/index.js`.
- State machine and validation in `src/core/shared/requestValidation.js`.
- Persistence and migration in `src/infrastructure/db/index.js`.
- Internal diagnostics/logs in `/internal/diagnostics` and `/internal/logs`.
- AI infrastructure registry in `src/infrastructure/ai/index.js`.

## AI runtime mode (current stage)
- Stage 1 is DeepSeek-focused foundation.
- Canonical config is normalized once in `src/infrastructure/config/index.js`, then reused by AI runtime/services.
- Business usage remains OFF by default (`AI_BUSINESS_USAGE_ENABLED=false`), so AI is not wired into business request flows.
- Diagnostics and runtime switching are active and operate on normalized canonical values.

## AI runtime settings (DB/meta)
Runtime overrides are stored in DB meta and can be changed without redeploy:
- `active_ai_provider` / `active_ai_model`
- `active_ai_fallback_provider` / `active_ai_fallback_model`
- `ai_enabled_runtime`
- `ai_business_usage_enabled_runtime`
- `last_ai_diagnostics_at` / `last_ai_diagnostics_status` / `last_ai_diagnostics_summary`

## AI env resolution visibility
- `/internal/diagnostics` returns resolved AI config and source metadata (which env key won during resolution).
- `/ai_status` and `/ai_diagnostics` show active provider/model plus resolved env source and legacy usage (masked secrets).
