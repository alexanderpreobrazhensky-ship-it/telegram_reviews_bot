# Project Overview

## What this project is
A Node-first multi-bot platform with one shared runtime:
- shared HTTP server
- shared WebApp
- Telegram client bot
- Telegram master bot
- Telegram integration bot
- MAX client bot
- MAX master bot
- SQLite persistence
- in-process persisted scheduler
- AI-ready infrastructure layer kept disabled by default

## Canonical production path
- `app.js`
- `src/server/index.js`
- `src/infrastructure/config/index.js`
- `src/infrastructure/db/index.js`
- `src/interfaces/client_bot/index.js`
- `src/interfaces/master_bot/index.js`
- `src/interfaces/integration_bot/index.js`
- `public/webapp.js`

## Current master-bot model
- Main menu is inline callback-based.
- Stable callbacks: `menu:new_requests`, `menu:in_progress`, `menu:archive`, `menu:search`, `menu:quality_cases`, `menu:instruction`, `menu:diagnostics`, `menu:logs`, `menu:access`.
- Request cards use: take in progress, ask client, processed, in service, complete, comment, details.
- Legacy inline callbacks are remapped and refreshed instead of surfacing raw transition failures.

## Current request lifecycle
Primary statuses:
- `new`
- `in_progress`
- `processed`
- `in_service`
- `completed`
- `error`

Processed substatuses:
- `recorded`
- `consulted`
- `spam`
- `waiting_decision`
- `rejected`

Archive is modeled by `archived=true`, not by a separate operational queue status.
