# Repository Full Audit

## Scope
Repository structure, the real Node-first production contour, supporting files, remaining legacy areas, and files that are still present but are not runtime source of truth.

## Current state
- The active production entrypoint is `app.js`, with the HTTP runtime created in `src/server/index.js`.
- Runtime-critical code is concentrated in `src/core/**`, `src/infrastructure/**`, `src/interfaces/**`, `src/integrations/**`, `public/**`, and the top-level deployment files `package.json`, `Dockerfile`, and `.bothost/entrypoint.conf`.
- The repository still contains historical Python and legacy folders (`bots/**`, `services/**`, `shared/clients_registry.py`, `legacy/index.js`), but they are not referenced by the active Node startup chain.
- Audit artifacts are concentrated under `audit/`, and operational prose docs are concentrated under `readme/`.

## Confirmed facts
### Confirmed by code
- `package.json` declares `main: "app.js"` and `npm start` runs `node app.js`.
- `.bothost/entrypoint.conf` points BotHost at `app.js`.
- `Dockerfile` also starts `node app.js`.
- `app.js` loads config, initializes the SQLite store, creates the HTTP server, and starts the in-process scheduler after `listen()` succeeds.
- `src/server/index.js` is the authoritative route map for health endpoints, internal HTML pages, API routes, static assets, and bot webhooks.
- Production WebApp code is `public/webapp.js`; the server injects runtime configuration into `public/index.html` at response time.
- Telegram client bot, Telegram master bot, Telegram integration bot, MAX client bot, and MAX master bot are all registered from `src/server/index.js` through `src/interfaces/**`.

### Confirmed by deployment-oriented files
- BotHost and container entrypoints both align with the Node-first runtime.
- There is no deployment file in the active contour that points production at the Python folders.

### Still hypothesis only
- The exact runtime contents mounted in the live BotHost instance are not provable from the repository alone.
- The exact set of files copied into the current production release cannot be confirmed without a runtime/deploy inspection.

## What changed after modernization
- P0/P1/P2-era modernization consolidated the production path around Node instead of the earlier mixed/tree-wide perception.
- The server now combines WebApp delivery, bot webhooks, internal operational pages, reports, integrations, and health endpoints in one Node process.
- SQLite-backed persistence under `src/infrastructure/db/index.js` replaced JSON-first persistence as the active source of truth, while keeping one-way JSON import compatibility.
- The audit baseline is now aligned to the active runtime rather than to the broad historical repository tree.

## Remaining gaps
- Legacy folders remain in-place, so a superficial repo scan can still overestimate their production relevance.
- There is no generated runtime manifest that labels directories as active, supporting, or legacy.
- `src/interfaces/webapp/routes.js` and `src/interfaces/webapp/state.js` still exist as lightweight scaffolding, which can mislead readers into treating them as the runtime routing source.

## Risks
- Future contributors may still read `bots/**` or `services/**` as active runtime code unless the Node-first contour is stated explicitly.
- Placeholder infrastructure knobs (`DB_DRIVER`, `DB_URL`, `QUEUE_DRIVER`, `ENABLE_INTEGRATION_WORKER`) can make the repo look more pluggable than it is.
- A deploy/config mismatch could still occur if an operator relies on legacy assumptions rather than the Node-first runtime path.

## Legacy / dead / misleading parts
- `bots/**`, `services/**`, and `shared/clients_registry.py` are legacy/supporting artifacts, not active production runtime.
- `legacy/index.js` is not part of the active startup chain.
- `src/interfaces/webapp/routes.js` and `src/interfaces/webapp/state.js` are not the authoritative route/source-of-truth layer for production WebApp delivery.
- The Python test files and Python service folders should not be used to describe the current production architecture.
- `review.html` and `public/index.html` remain present but were not used as audit rewrite targets.

## Confidence level
High for repository shape and production-relevant code paths; medium for live deploy packaging details because runtime inspection was not part of this pass.

## Recommended follow-up checks
- Verify the live BotHost release really starts from `app.js` and not an older artifact.
- Add a simple active-vs-legacy repository map to reduce future drift.
- If legacy Python folders are no longer needed, archive or clearly mark them to reduce architectural ambiguity.
