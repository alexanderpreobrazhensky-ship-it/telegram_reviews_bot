# MASTER AUDIT FOR EXTERNAL AI

## 1) Branch / production targeting
- Рабочая ветка в локальном репо: `work`.
- Зафиксированный production-контракт: **deploy branch = `main`**.
- Рекомендация: поддерживать `main` как единственную ветку для BotHost деплоя.

## 2) Production runtime contract
- Runtime: **Python-first**.
- Deploy path: **Dockerfile-first**.
- Entrypoint: корневой `main.py`.
- Runtime chain: `main.py` → `services/client_bot_service/app/main.py` → `bots/client_bot/main.py`.
- `index.js` оставлен как compatibility-only и не является production entrypoint.

## 3) Entrypoints and deploy files
- `Dockerfile` запускает `CMD ["python", "main.py"]`.
- `.bothost/entrypoint.conf` содержит `main_file=main.py` и `branch=main` как compat-hint для платформы.
- Основной deploy-документ: `README.md`.

## 4) Webhook-first runtime behavior
- Default mode: `webhook`.
- Base URL priority: `WEBHOOK_URL` → `PUBLIC_BASE_URL` → `DOMAIN`.
- URL normalization: trim, scheme-fix, lowercase host, invalid URL => empty.
- `BOT_PATH_SECRET` обязателен для webhook (`RuntimeError` если отсутствует).
- Если base URL не собран/invalid: warning + fallback в polling.
- На старте логируются: `mode`, `token_source`, `base_url_source`, `port`, `storage_mode`, `env_used_count`, `env_ignored_count`.

## 5) ENV audit (required/recommended/optional)
### Required (webhook-first)
- `CLIENT_TELEGRAM_BOT_TOKEN` (или alias)
- `BOT_PATH_SECRET`
- один из `WEBHOOK_URL|PUBLIC_BASE_URL|DOMAIN`

### Recommended
- `PORT`
- `TIMEZONE`
- `CLIENT_WEBAPP_SESSION_SECRET`
- `CLIENT_MASTERS_CHAT_ID` (или alias)

### Optional / legacy
- Alias-цепочки токена/режима/порта/base URL/WebApp URL/masters id поддерживаются для совместимости.
- `index.js` и `.bothost/entrypoint.conf` — compatibility слой.

## 6) HTTP routes verified by tests
- `/health`
- `/service-health`
- `/WEBAPP`, `/WEBAPP/`
- `/WEBAPP/config.json`
- `/assets/webapp.bundle.js`
- `/assets/webapp.bundle.css`
- `/app.js`
- `/app.css`

## 7) Risks eliminated
- Runtime ambiguity (Node vs Python) снижена до compatibility-only уровня.
- README drift между root и `bots/client_bot/README.md` устранён.
- Dockerfile/main.py production-contract зафиксирован тестами.

## 8) Remaining risks / known limitations
- Локальная ветка сейчас `work`; для прод-процесса нужен merge/sync в `main`.
- Широкий env surface (много alias) увеличивает стоимость поддержки.
- Webhook fallback в polling может скрывать ошибки конфигурации base URL.

## 9) Stable deployment blockers (most likely)
- Не задан токен.
- Не задан `BOT_PATH_SECRET` при `webhook`.
- Не задан ни один base URL источник.
- Платформа развернула не `main`.

## 10) Verification commands
1. `python -m unittest discover -s tests -p "test_*.py"`
2. `python -m unittest tests/test_entrypoints.py`
3. `python -m unittest tests/test_webhook_url_build.py`

## 11) BotHost recommendations
- Branch: `main`
- Use custom Dockerfile: enabled
- Main file (if required by UI): `main.py`
- Проверки после запуска: `/health`, `/WEBAPP`, `getWebhookInfo`
