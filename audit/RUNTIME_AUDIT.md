# Runtime Audit

## Scope
Entrypoint, startup chain, route registration, scheduler behavior, WebApp delivery, and the boundary between code-confirmed runtime facts and deploy-only assumptions.

## Current state
- The production runtime is a single Node.js HTTP process started from `app.js`.
- The app uses Node's built-in `http` server rather than Express or another framework.
- WebApp routes, API routes, internal pages, health checks, and bot webhooks share the same process.
- The scheduler is in-process and starts only after the server begins listening.

## Confirmed facts
### Confirmed by code
- `app.js` calls `loadConfig()`, logs DB runtime info, initializes the store, creates the server, configures the scheduler, and starts the scheduler inside the `listen()` callback.
- `src/server/index.js` registers bot routes before request handling begins.
- Health endpoints are `/health`, `/health/db`, and `/health/max`.
- Internal operational pages are served at `/internal/requests`, `/internal/requests/:id`, and `/internal/export`.
- Static assets are served directly from `public/` for `/styles.css`, `/webapp.js`, and `/logo.png`.
- WebApp HTML for `/`, `/requests`, `/recommendations`, and the five `/forms/...` routes is always served from `public/index.html` with injected runtime config.
- Webhook requests are subject to an in-memory rate limiter keyed by path and request IP.
- WebApp request creation routes are separately rate-limited and dedupe-checked.
- Scheduler handlers are configured in `app.js`; only `feedback_request` currently has implemented outbound behavior, while `quality_followup`, `recommendation_reminder`, and `maintenance_reminder` are placeholders.

### Confirmed by deployment-oriented files
- BotHost and Docker both point at the same `app.js` startup path.
- The runtime expects a writable filesystem location for SQLite.

### Confirmed only by deployment assumptions, not by repo runtime proof
- BotHost is assumed to preserve the configured SQLite path across restarts/redeploys.
- Telegram and MAX webhook endpoints are assumed to be registered with their external platforms.
- Network egress to Telegram and MAX APIs is assumed to be available in production.

### Unresolved runtime uncertainty
- Whether production runs a single instance or multiple instances is not confirmed from code or deploy files here.
- Whether the live environment uses strict config mode is not confirmed.
- Whether the live deployment exposes integration endpoints publicly or behind additional proxy controls is not confirmed.

## What changed after modernization
- The runtime path is now explicitly Node-first, centralized in `app.js` and `src/server/index.js`.
- Persistence startup is now SQLite-centric, with DB runtime logging and initialization happening before server start.
- WebApp delivery, admin pages, integrations, reporting, and bots now live behind a unified HTTP server instead of appearing as scattered legacy surfaces.
- Scheduler behavior is codified as an in-process runtime responsibility rather than an external worker assumption.

## Remaining gaps
- No process supervisor logic or cluster coordination exists in the repo.
- No startup manifest endpoint summarizes registered routes or enabled contours.
- No separate worker isolates scheduler/task execution from request-handling load.
- In-memory rate limiting and sessions remain instance-local.

## Risks
- Single-process design means webhook bursts, internal reports, and scheduler work share one failure domain.
- In-memory sessions in bot handlers are lost on restart.
- Instance-local rate limiting and scheduler logic can misbehave under uncoordinated horizontal scaling.
- Runtime health endpoints may appear healthy even if outbound bot tokens are missing.

## Legacy / dead / misleading parts
- `src/interfaces/webapp/routes.js` is not the authoritative runtime route map.
- Legacy Python folders describe an older shape and must not be treated as the active runtime contour.
- Placeholder env values such as `ENABLE_INTEGRATION_WORKER` can imply a worker topology that does not exist yet.

## Confidence level
High for code-confirmed runtime flow; medium for production hosting behavior because no live runtime inspection was performed.

## Recommended follow-up checks
- Verify the live process is launched from `app.js` and that scheduler logs appear after server start.
- Confirm persistence survives a real BotHost restart on the configured SQLite path.
- If multi-instance deployment is planned, re-audit scheduler, dedupe, rate limiting, and bot sessions immediately.
