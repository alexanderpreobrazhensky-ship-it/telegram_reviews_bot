# Operations

## Recommended smoke checks after deploy
1. `GET /health`
2. `GET /health/db`
3. `GET /health/max`
4. open `/` and one form route
5. submit one request through WebApp
6. verify Telegram client bot `/start`
7. verify Telegram master bot `/start` with an allowed admin
8. verify Telegram integration bot `/start` if token is configured
9. verify MAX webhooks if MAX is enabled
10. restart once and confirm SQLite data still exists

## Operational caveats
- Missing Telegram/MAX tokens do not always kill webhook routes; they can degrade outbound delivery instead.
- Internal routes rely on env allowlists, not sessions.
- Integration endpoints currently need stronger auth before broader exposure.
