# AUDIT_AFTER_CODEX.md

## 1) Итог по задаче
Репозиторий приведён к схеме запуска **BotHost Node bootstrap → Python**. BotHost запускает `index.js`, который запускает `python main.py`; Python поднимает Flask, webhook/polling логику и WebApp-статику.

## 2) Ключевое дерево
- `index.js` — единый BotHost entrypoint
- `main.py` — тонкий Python entrypoint
- `services/client_bot_service/app/main.py` — orchestration startup
- `services/client_bot_service/app/config.py` — централизованный env-resolve
- `bots/client_bot/main.py` — Telegram/webhook/routes/runtime
- `bots/client_bot/webapp/index.html`
- `bots/client_bot/webapp/assets/webapp.bundle.js`
- `bots/client_bot/webapp/assets/webapp.bundle.css`
- `bots/client_bot/webapp/config.json`

## 3) Точный runtime pipeline
1. `node index.js`
2. `spawn("python", ["main.py"], {stdio:"inherit", env:process.env})`
3. `main.py` → `services.client_bot_service.app.main.main()`
4. Service startup (webhook-first):
   - resolve env
   - `deleteWebhook(drop_pending_updates=True)`
   - `setWebhook(url=...)` (если собран URL)
   - `app.run(host, port)`
5. Если webhook URL не собран: warning + fallback в polling (после `deleteWebhook`)

## 4) Диагностические логи старта
Добавлен startup-лог формата:
- `effective_runtime=node_bootstrap`
- `python_entrypoint=main.py`
- `mode=webhook|polling`
- `webhook_url=<masked>`
- `token_source=...`
- `port=...`
- `host=...`

## 5) Webhook URL формирование
Приоритет base:
1. `WEBHOOK_URL`
2. `PUBLIC_BASE_URL`
3. `DOMAIN` (приведение к `https://...`)

Path: `/webhook/<BOT_PATH_SECRET>`.

Правила:
- В webhook mode отсутствие `BOT_PATH_SECRET` → `RuntimeError`.
- Если base URL невалиден/пуст — fallback в polling с предупреждением.

## 6) Маршруты WebApp и статики
Поддерживаются:
- `GET /WEBAPP`, `GET /WEBAPP/` → `index.html`
- `GET /assets/webapp.bundle.js`
- `GET /assets/webapp.bundle.css`
- `GET /WEBAPP/config.json`
- Алиасы: `GET /app.js`, `GET /app.css`

Для статики выставляется:
- `Cache-Control: no-cache, no-store, must-revalidate, max-age=0`

## 7) Очистка от legacy-hosting / Node автодетекта
- В root отсутствуют `package.json`, `app.js`, `server.js`, `main.js`, `Procfile`, `legacy-hosting.toml`.
- Для запуска остаётся только `index.js` как Node bootstrap.

## 8) ENV matrix (client-bot runtime)
| ENV | Required | Где используется | Формат | Default | Алиасы / приоритет |
|---|---|---|---|---|---|
| CLIENT_TELEGRAM_BOT_TOKEN | required | `services/client_bot_service/app/config.py` | string | - | primary token |
| TELEGRAM_BOT_TOKEN | optional | `.../config.py` | string | - | token fallback #1 |
| BOT_API_TOKEN | optional | `.../config.py` | string | - | token fallback #2 |
| API_TOKEN | optional | `.../config.py` | string | - | token fallback #3 |
| BOT_TOKEN | optional | `.../config.py` | string | - | token fallback #4 |
| TOKEN | optional | `.../config.py` | string | - | token fallback #5 |
| CLIENT_BOT_MODE | recommended | `.../config.py` | enum(webhook/polling) | webhook | - |
| BOT_PATH_SECRET | required for webhook | `.../config.py`, `bots/client_bot/main.py` | string | - | webhook path secret |
| WEBHOOK_URL | recommended | `.../config.py`, `bots/client_bot/main.py` | URL | - | base #1 |
| PUBLIC_BASE_URL | optional | `.../config.py`, `bots/client_bot/main.py` | URL | - | base #2 |
| DOMAIN | optional | `.../config.py`, `bots/client_bot/main.py` | host/url | - | base #3 (normalized) |
| PORT | recommended | `.../config.py`, `bots/client_bot/main.py` | int | 8000 | port #1 |
| CLIENT_SERVICE_PORT | optional | `.../config.py`, `bots/client_bot/main.py` | int | 8000 | port #2 |
| CLIENT_SERVICE_HOST | optional | `.../config.py` | host | 0.0.0.0 | - |
| CLIENT_WEBAPP_URL | optional | `.../config.py`, `bots/client_bot/main.py` | URL | - | webapp explicit #1 |
| WEBAPP_URL | optional | `.../config.py`, `bots/client_bot/main.py` | URL | - | webapp explicit #2 |
| WEBAPP_PATH | optional | `.../config.py`, `bots/client_bot/main.py` | path | /WEBAPP | - |
| DATABASE_URL | optional | `.../config.py`, `bots/client_bot/main.py` | URL | - | db #1 |
| POSTGRES_URL | optional | `.../config.py`, `bots/client_bot/main.py` | URL | - | db #2 |
| POSTGRESQL_URL | optional | `.../config.py`, `bots/client_bot/main.py` | URL | - | db #3 |
| CLIENT_MASTER_USER_IDS | optional | `.../config.py`, `bots/client_bot/main.py` | csv<int> | "" | primary masters list |
| CLIENT_MASTER_IDS | optional | `.../config.py`, `bots/client_bot/main.py` | csv<int> | "" | alias masters list |
| CLIENT_MASTERS_CHAT_ID | optional | `.../config.py`, `bots/client_bot/main.py` | int | "" | primary masters chat |
| CLIENT_MASTER_CHAT_ID | optional | `.../config.py`, `bots/client_bot/main.py` | int | "" | alias masters chat |
| CLIENT_CHAT_ID | optional | `.../config.py`, `bots/client_bot/main.py` | int | "" | alias masters chat |

## 9) Добавленные/обновлённые smoke/contract тесты
- `tests/test_bothost_contract.py`
  - наличие `index.js` и отсутствие node-entrypoint файлов
  - root `main.py` импортирует service entrypoint
  - приоритеты PORT
  - приоритеты token
  - приоритеты webhook base URL + нормализация DOMAIN
- `tests/test_webapp_static_routes.py`
  - `200 OK` на `/WEBAPP`, `/assets/webapp.bundle.js`, `/assets/webapp.bundle.css`, `/app.js`, `/app.css`

## 10) Операционный checklist для BotHost
1. Main file = `index.js`.
2. Установить env: `CLIENT_TELEGRAM_BOT_TOKEN`, `BOT_PATH_SECRET`, `WEBHOOK_URL` (или `PUBLIC_BASE_URL`/`DOMAIN`).
3. Проверить `GET /health` и `GET /service-health`.
4. Проверить `getWebhookInfo`.
5. В BotFather обновить Main App/Menu Button URL на `https://<bothost-domain>/WEBAPP`.
