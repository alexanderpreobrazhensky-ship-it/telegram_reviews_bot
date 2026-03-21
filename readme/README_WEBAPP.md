# WebApp

## Served pages
- `/`
- `/requests`
- `/recommendations`
- `/forms/service-request`
- `/forms/parts-request`
- `/forms/consultation`
- `/forms/warranty-request`
- `/forms/data-change-request`

## Behavior
- Shell comes from `public/index.html`.
- Logic lives in `public/webapp.js`.
- Runtime config is injected by the server.
- Form submit APIs live under `/api/client/requests/*`.

## Phone rule
- Store only 10 digits.
- Strip `+7` / `8` prefixes.
- Validate on both client and server.

## Identity
- Telegram WebApp uses `Telegram.WebApp.initDataUnsafe.user.id` when available.
- MAX WebApp uses `MAX.WebApp.initDataUnsafe.user.id` when available.
- This is runtime-derived identity, not cryptographically verified identity.
