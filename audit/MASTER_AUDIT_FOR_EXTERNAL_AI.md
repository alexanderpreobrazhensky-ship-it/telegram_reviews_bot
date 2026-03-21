# Master audit for external AI

## Canonical runtime contract
- Runtime: Node.js.
- Entrypoint: `app.js`.
- Package manifest: `package.json`.
- Container start command: `node app.js`.
- BotHost entrypoint: `.bothost/entrypoint.conf` with `main_file=app.js`, `branch=main`.

## Scope snapshot
- Shared HTTP server, WebApp, scheduler, Telegram client/master/integration bots, and MAX client/master bots all run in one process.
- Persistence is a JSON file via `DB_FILE_PATH`.
- The repository also contains a legacy Python contour that is not part of the active production path.

## Current readiness summary
- Node/BotHost readiness: moderate/good for single-instance deployment.
- MAX readiness: partial-to-good MVP.
- Security readiness: partial due to unauthenticated integration routes.
- Persistence readiness: partial due to JSON DB limitations.
- Documentation consistency: restored in this audit pass.

## Main blockers and caveats
1. JSON DB is not scale-safe.
2. Integration HTTP routes need auth hardening.
3. No MAX integration bot route.
4. Recommendation parity for MAX is incomplete.
5. Legacy Python files remain a maintenance/documentation drift risk.
