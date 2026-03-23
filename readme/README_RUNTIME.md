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
- AI-ready provider registry in `src/infrastructure/ai/index.js`.
