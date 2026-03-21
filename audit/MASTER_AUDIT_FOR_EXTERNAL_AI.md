# Master Audit for External AI

## Scope
A compact source-of-truth brief for a future GPT agent that needs to operate on the repository without re-discovering the entire production shape.

## Current state
- Canonical runtime: Node.js monolith rooted at `app.js`.
- Canonical DB: SQLite via `src/infrastructure/db/index.js`.
- Canonical router: `src/server/index.js`.
- Canonical frontend runtime: `public/webapp.js` plus `public/index.html` shell.

## Confirmed facts
- Node-first backend is the only active production contract.
- Separate new BotHost project for MAX is forbidden; MAX stays embedded in the same Node foundation.
- `review.html` and `public/index.html` were not modified in this audit pass.
- Admin bootstrap is env-driven; manager/master access is granted through bot access flow.
- Phone must be stored as 10 digits without `+7/8`.
- Recommendations are only materially valid when real 1C sync populates them.
- Integration bot remains Telegram-only.

## Risks
- Unauthenticated integration endpoints.
- Single-process runtime and in-memory sessions.
- Legacy Python drift risk.
- MAX still foundation-grade rather than full-parity hardened.

## Gaps
- Live deploy state cannot be proven purely from repo contents.
- WebApp identity verification is not cryptographic.

## Legacy / dead / misleading parts
- `bots/**`, `services/**`, `shared/clients_registry.py`, and `legacy/index.js` are not the active runtime.
- `src/interfaces/webapp/routes.js` is not authoritative routing.

## Recommendations
1. Start all future reasoning from `app.js`, `src/server/index.js`, `src/infrastructure/config/index.js`, `src/infrastructure/db/index.js`, bot handlers, and `public/webapp.js`.
2. Treat Telegram as the more mature channel and MAX as the tested but still partially confirmed contour.
3. Prioritize security/auth work on integration endpoints and identity verification if product scope expands.

## Confidence level
High.

## Follow-up checks
- Re-run `npm test` after any runtime change.
- Re-validate MAX and Telegram on live platforms after deploy-facing changes.
