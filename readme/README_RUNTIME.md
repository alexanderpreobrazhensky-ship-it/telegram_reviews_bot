# Runtime

## Startup chain
1. `app.js` loads config.
2. SQLite runtime info is logged and the store is initialized.
3. `createServer()` builds the HTTP server.
4. Bot webhook routes are registered.
5. Scheduler is created.
6. `server.listen()` starts the app.
7. Scheduler starts after listen succeeds.

## Runtime model
- Single Node.js process.
- Node `http.createServer`, not Express.
- Shared event loop for HTTP, bots, and scheduler.
- Static WebApp served from `public/`.

## Main route groups
- Health: `/health`, `/health/db`, `/health/max`
- Internal admin: `/internal/requests`, `/internal/export`
- WebApp pages: `/`, `/requests`, `/recommendations`, `/forms/...`
- Client request APIs: `/api/client/requests/*`
- Analytics/reporting APIs
- Telegram webhooks
- MAX webhooks
