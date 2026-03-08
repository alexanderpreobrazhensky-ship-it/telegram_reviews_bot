# AUDIT_AFTER_CODEX

## What was broken
- BotHost could choose Node runtime due to `index.js` and fail before Python startup.
- Production docs pointed to Node bootstrap instead of stable Python-first contract.
- No root Dockerfile contract for BotHost custom Dockerfile mode.

## Why it failed
- Mixed runtime entrypoints (Node + Python) created ambiguous platform autodetection.
- Deploy instructions and BotHost config were not aligned with webhook-first Python runtime.

## What was changed
- Added root `Dockerfile` for Python-only runtime (`CMD ["python", "main.py"]`).
- Kept root `main.py` as single production entrypoint and added explicit startup marker log.
- Updated `.bothost/entrypoint.conf` to `main.py` for compatibility.
- Updated tests to assert Dockerfile entrypoint and root-main contract.
- Expanded webhook URL normalization tests.
- Added runtime behavior tests:
  - master-chat plain text is ignored (no ticket creation path)
  - webhook mode calls `setWebhook`
  - webhook fallback calls `deleteWebhook(...drop_pending_updates=True)` then polling
- Rewrote `README.md` to Dockerfile-first / Python-only deploy contract and env grouping.

## Removed / retained
- Removed:
  - runtime data artifacts from VCS (`data/*.jsonl`, `data/system.json`)
  - legacy `review.html` not used by client-bot runtime/tests/deploy.
- Retained intentionally:
  - `bots/client_bot/webapp/index.html`
  - `logo.png`
  - `index.js` as legacy compatibility artifact (not production-recommended path)
  - `data/.gitkeep` to preserve runtime data directory in clean repository.

## Current deploy contract
- BotHost: enable custom Dockerfile.
- Container entrypoint: `python main.py`.
- Runtime mode default: `webhook`.
- Webhook URL source priority: `WEBHOOK_URL` → `PUBLIC_BASE_URL` → `DOMAIN`.
- Polling fallback only when webhook base URL cannot be built.

## Post-change validation
### Unit tests result
- `python -m unittest discover -s tests -p "test_*.py"` should pass.

### Expected BotHost setup
- Branch: `main`
- Use custom Dockerfile: enabled
- Runtime path: Dockerfile build/run

### Expected runtime logs
- startup marker: `LIRA client-bot starting (root main.py)`
- mode / token source / base_url source / port / storage_mode / env_used_count / env_ignored_count
- webhook ready log with masked secret path

### Expected HTTP checks
- `GET /health` → 200 + `{status:"ok", service:"client-bot", mode:"webhook|polling"}`
- `GET /service-health` → 200
- `GET /WEBAPP` and static aliases (`/assets/...`, `/app.js`, `/app.css`, `/WEBAPP/config.json`) → 200
