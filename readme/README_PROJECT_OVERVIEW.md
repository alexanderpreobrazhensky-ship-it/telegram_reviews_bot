# Project Overview

## What this project is
A Node.js-first BotHost-safe service that combines:
- shared HTTP server
- shared WebApp
- Telegram client bot
- Telegram master bot
- Telegram integration bot
- MAX client bot
- MAX master bot
- SQLite-backed operational storage
- in-process scheduler for follow-up tasks

## Canonical production path
- `app.js`
- `src/server/index.js`
- `src/infrastructure/config/index.js`
- `src/infrastructure/db/index.js`
- `src/interfaces/client_bot/index.js`
- `src/interfaces/master_bot/index.js`
- `src/interfaces/integration_bot/index.js`
- `public/webapp.js`

## Hard rules to keep in mind
- Backend is Node-first only.
- MAX stays inside the current project; no separate BotHost project.
- `review.html` and `public/index.html` are not to be edited casually.
- Admin bootstrap is env-driven.
- Manager/master access is granted through bot flows.
- Phone is stored as 10 digits without `+7/8`.
- Recommendations only become meaningful after real 1C sync.
- Integration bot remains Telegram-only.

## What is not canonical
- `bots/**`, `services/**`, `shared/clients_registry.py`, and `legacy/index.js` are legacy/historical.
