# Manual upload guide (if BotHost/Git sync is unstable)

Если сервер/интеграция временно не тянет автодеплой, можно вручную загрузить **полные файлы** из этого коммита.

## Critical files to upload first

1. `index.js`
2. `main.py`
3. `services/client_bot_service/app/main.py`
4. `services/client_bot_service/app/config.py`
5. `bots/client_bot/main.py`
6. `README_AFTER_DEPLOY.md`
7. `AUDIT_AFTER_CODEX.md`
8. `.bothost/entrypoint.conf` (если BotHost читает локальные подсказки)

## Also upload tests/CI (recommended)

- `.github/workflows/tests.yml`
- `tests/test_bothost_entrypoint.py`
- `tests/test_webhook_url_build.py`
- `tests/test_webapp_static_routes.py`
- `tests/test_health.py`

## Remove legacy files on server (if still present)

- `review.html`
- `bots/client_bot/webapp/webapp.js`
- `bots/client_bot/webapp/webapp.css`

## Minimal post-upload check

- BotHost main file: `index.js`
- `GET /health` -> 200 JSON
- `GET /WEBAPP` -> 200
- `GET /assets/webapp.bundle.js` -> 200
- `GET /assets/webapp.bundle.css` -> 200

## Local commands before packaging

```bash
python -m unittest discover -s tests -p "test_*.py"
```

## Build one zip for transfer

```bash
zip -r client-bot-manual-upload.zip \
  index.js main.py \
  services/client_bot_service \
  bots/client_bot \
  README_AFTER_DEPLOY.md AUDIT_AFTER_CODEX.md MANUAL_UPLOAD_GUIDE.md \
  .github/workflows/tests.yml tests .bothost
```

После ручной загрузки перезапустите сервис и проверьте логи на строки:
- `effective_bot=client`
- `mode=webhook`
- `setWebhook ok`
