# Runtime Audit

## Scope
Entrypoint, startup chain, server creation, scheduler initialization, route registration, runtime assumptions, and deploy-dependent behavior.

## Current state
- `app.js` is the real bootstrap.
- Startup order is: load config → inspect/init SQLite → create HTTP server → configure scheduler → `listen()` → start scheduler.
- `src/server/index.js` uses Node `http.createServer`, not Express.
- Telegram client, Telegram master, Telegram integration, MAX client, and MAX master webhook handlers all run in the same process.

## Confirmed facts
- Real entrypoint: `app.js`.
- Real server factory: `createServer({ config, logger })` in `src/server/index.js`.
- Route registration for bots happens synchronously during server creation via `registerClientBotRoutes`, `registerMasterBotRoutes`, and `registerIntegrationBotRoutes`.
- Scheduler is created in `app.js` and starts only after `server.listen()` succeeds.
- Scheduler processing shares the same process and event loop with HTTP handling.
- WebApp delivery is static-file based: `public/index.html`, `public/styles.css`, and `public/webapp.js`, with runtime config injected into HTML at response time.

## Runtime assumptions
### Confirmed facts
- The app expects a writable filesystem path for SQLite.
- Telegram outbound delivery requires token presence but webhook handlers can still accept requests without tokens.
- MAX routes require `MAX_ENABLED`, the relevant token, and `MAX_WEBHOOK_SECRET` to accept webhook payloads.

### Depends on ENV
- Listen port, scheduler timing, admin bootstrap, MAX availability diagnostics, WebApp URLs, rate limits, and dedupe windows.

### Depends on deploy environment
- Persistence durability depends on how BotHost mounts the DB path.
- External message delivery depends on Telegram/MAX API availability.
- Real MAX/Telegram webhook registration must be done outside the app.

### Assumptions / hypotheses only
- BotHost persistence guarantees are not provable from source alone.
- Real live webhook registration state is not visible inside the repository.

## Risks
- Single-process runtime means HTTP load, webhook bursts, and scheduler work share one failure domain.
- In-memory bot sessions are lost on restart.
- Rate limiting is in-memory and therefore instance-local.

## Gaps
- No separate worker process for scheduler/integration tasks.
- No route auto-registration report exposed to operators.
- No environment-specific startup mode that disables unsupported contours entirely.

## Legacy / dead / misleading parts
- `src/interfaces/webapp/routes.js` is not the live route source.
- Legacy Python services describe a different startup model and must not be used for runtime reasoning.

## Recommendations
1. Keep treating the platform as a single-instance/small-scale monolith unless worker separation is added.
2. If multi-instance deploys are planned, move rate limiting, dedupe, and scheduling coordination out of process memory.
3. Add a runtime manifest endpoint or startup log summarizing registered routes and enabled contours.

## Confidence level
High.

## Follow-up checks
- Validate actual webhook registration in Telegram/MAX control planes after each deploy.
- Verify BotHost persistent volume behavior against the configured SQLite path.
