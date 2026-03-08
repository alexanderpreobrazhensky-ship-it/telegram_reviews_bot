# MASTER AUDIT FOR EXTERNAL AI

## 1. Executive summary
- Проект: Telegram client-bot на Python (Flask + Telegram API), с WebApp-статикой в `bots/client_bot/webapp`.
- Фактическая production-цепочка запуска: `python main.py` -> `services/client_bot_service/app/main.py` -> `bots/client_bot/main.py`.
- Репозиторий содержит также Node-обертку `index.js`, но она только запускает Python-процесс (`spawn('python', ['main.py'])`).
- Основной режим по коду: `webhook` (default), с автоматическим fallback в `polling`, если base URL невалиден/отсутствует.
- Ключевые риски: множественные entrypoints (Python + Node wrapper), широкие env-алиасы, webhook/polling конфликтный контур, legacy-переменные в документации, неоднозначности around BotHost runtime selection.

## 2. Repository snapshot
- Current working branch (local): `work`
- Production deployment branch target: `main`
- Commit: `2cafd4b28b71500c98cb7c750bda679bdc44f840`
- Tracked files manifest: `audit/REPO_MANIFEST.txt`

### Ключевое дерево

### Repository cleanliness updates
- Removed legacy non-runtime artifact: `review.html`.
- Removed tracked runtime data snapshots (`data/clients.jsonl`, `data/tickets.jsonl`, `data/system.json`).
- Added `.gitignore` rules to keep runtime-generated data out of VCS and retained only `data/.gitkeep`.
- `main.py` — root Python entrypoint.
- `index.js` — Node bootstrap, запускающий Python.
- `services/client_bot_service/app/main.py` — сервисный shim entrypoint.
- `services/client_bot_service/app/config.py` — runtime/env selection слой.
- `bots/client_bot/main.py` — главный runtime (бот-логика, Flask routes, webhook/polling).
- `bots/client_bot/services/*.py` — AI, Telegram API transport, outgoing queue.
- `bots/client_bot/storage.py` — локальная персистентность + GitHub sync hooks.
- `shared/clients_registry.py` — общий jsonl реестр клиентов.
- `bots/client_bot/webapp/*` — webapp статика (`index.html`, бандлы, config.json).
- `.github/workflows/tests.yml` — CI юнит-тесты.
- `.bothost/entrypoint.conf` — BotHost совместимость-конфиг.
- `Dockerfile` — Docker runtime.
- `requirements.txt` и `bots/client_bot/requirements.txt` — Python deps.

## 3. Entrypoints and startup chain
### Найденные entrypoints
1. `main.py` (root Python): вызывает `service_main()`.
2. `services/client_bot_service/app/main.py`: вызывает `bots.client_bot.main.main()`.
3. `bots/client_bot/main.py`: конечный runtime.
4. `index.js`: Node-обертка, которая запускает `python main.py`.
5. `start_polling_background()` в `bots/client_bot/main.py`: альтернативный вспомогательный entrypoint для фонового polling-потока.

### Фактически основной
- Для Docker/README контрактов основной: `python main.py`.
- Для платформ с Node autostart потенциально может сработать `index.js`, но он все равно переходит в Python.

### Цепочка запуска (факт)
1. Получение runtime config через `load_runtime_config()`.
2. Инициализация логгера/telegram/db/storage/workers.
3. Если mode=`webhook`:
   - строится URL (`WEBHOOK_URL` -> `PUBLIC_BASE_URL` -> `DOMAIN`) + `/webhook/<BOT_PATH_SECRET>`;
   - `deleteWebhook(drop_pending_updates=True)`;
   - `setWebhook(url=...)`;
   - старт Flask (`app.run(host, port)`).
4. Иначе (или fallback) mode=`polling`:
   - `deleteWebhook(drop_pending_updates=True)`;
   - `poll_updates()` long polling loop.

### По средам
- BotHost: `.bothost/entrypoint.conf` указывает `main.py`; в репо также есть `index.js` совместимости.
- Docker: `CMD ["python", "main.py"]`.
- Local: `python main.py`.
- CI: только тесты, не деплой.

## 4. Runtime model
### Python runtime
- Основной runtime: Python 3.11 + Flask + requests + openai + psycopg.
- Основной веб-сервер запускается встроенным Flask `app.run(...)`.

### Node runtime
- Node используется только как launcher (`index.js`), не содержит бизнес-логики API.
- `index.js` прокидывает `process.env` и сигналы в дочерний Python процесс.

### Docker runtime
- `python:3.11-slim`, установка зависимостей из `requirements.txt`, запуск `python main.py`.

### Webhook vs polling
- Default mode normalizer: `webhook`.
- При `webhook` mode без валидного base URL логика делает fallback в polling.
- Polling также пытается разрешать 409 конфликт, вызывая `delete_webhook`.

### Прод-модель и конфликтные режимы
- Продовый контракт README: webhook-first, Dockerfile-first, Python-only.
- Конфликтный фактор: наличие Node wrapper + исторические polling-инструкции в `bots/client_bot/README.md`.

## 5. Full ENV audit
Статусы: `runtime_used`, `documented_only`, `ci_only`, `legacy_suspected`, `unused_suspected`.

Сводка: полный список окружения и источников собран в машинном виде в `audit/MASTER_AUDIT_FOR_EXTERNAL_AI.json` (ключ `env`). Ниже — condensed таблица с критичными переменными и alias-chain.

| ENV_NAME | required? | default | type | aliases | status | used_in | purpose |
|---|---|---|---|---|---|---|---|
| CLIENT_TELEGRAM_BOT_TOKEN | required | none | secret | TELEGRAM_BOT_TOKEN,BOT_API_TOKEN,API_TOKEN,BOT_TOKEN,TOKEN | runtime_used | services/client_bot_service/app/config.py:5-12,65-69 | основной токен |
| CLIENT_BOT_MODE | optional | webhook | string | CLIENT_RUN_MODE,RUN_MODE | runtime_used | services/client_bot_service/app/config.py:14,52-55 | режим |
| PORT | optional | 8000 | int | CLIENT_SERVICE_PORT | runtime_used | services/client_bot_service/app/config.py:15,75-77 | http port |
| WEBHOOK_URL | conditional | none | url | PUBLIC_BASE_URL,DOMAIN | runtime_used | bots/client_bot/main.py:653-663 | webhook base |
| BOT_PATH_SECRET | conditional(webhook) | none | secret | none | runtime_used | bots/client_bot/main.py:666-669,3533-3535 | webhook secret path |
| CLIENT_WEBAPP_ENABLED | optional | 1 | bool | WEBAPP_ENABLED | runtime_used | bots/client_bot/main.py:287-292 | webapp routes toggle |
| CLIENT_WEBAPP_URL | optional | none | url | WEBAPP_URL | runtime_used | bots/client_bot/main.py:695-701 | public webapp URL |
| CLIENT_WEBAPP_SESSION_SECRET | optional | BOT_PATH_SECRET | secret | BOT_PATH_SECRET | runtime_used | bots/client_bot/main.py:3278 | webapp session signing |
| CLIENT_MASTERS_CHAT_ID | optional | none | int | CLIENT_MASTER_CHAT_ID | runtime_used | bots/client_bot/main.py:302 | masters chat |
| CLIENT_MASTER_USER_IDS | optional | none | list[int] | CLIENT_MASTER_IDS | runtime_used | bots/client_bot/main.py:303,1498-1506 | masters list |
| CLIENT_ADMIN_IDS | optional | none | list[int] | ADMIN_IDS,SUPERADMIN_ID,SUPERADMIN_IDS | runtime_used | bots/client_bot/main.py:1506-1538 | admin bootstrap |
| MASTER_USERNAMES | optional | empty | list[string] | none | runtime_used | bots/client_bot/main.py:1086,1100 | master usernames |
| CLIENT_DEEPSEEK_API_KEY | optional | empty | secret | none | runtime_used | bots/client_bot/services/ai_service.py:54 | AI key |
| CLIENT_AI_TIMEOUT_SECONDS | optional | 10 | int | none | runtime_used | bots/client_bot/services/ai_service.py:81-88 | AI timeout |
| CLIENT_FORCE_FALLBACK | optional | 0 | bool | FORCE_FALLBACK | runtime_used | bots/client_bot/services/ai_service.py:58-61 | AI fallback control |
| DATABASE_URL | optional | none | url | POSTGRES_URL,POSTGRESQL_URL | runtime_used | bots/client_bot/main.py:346-355 | DB URL |
| CLIENT_GITHUB_TOKEN | optional | empty | secret | GITHUB_TOKEN | runtime_used | bots/client_bot/storage.py:59 | github sync |
| CLIENTS_REGISTRY_PATH | optional | repo default | path | none | runtime_used | shared/clients_registry.py:23-27 | registry override |
| TELEGRAM_BOT_TOKEN_CLIENT | optional | none | secret | CLIENT_TELEGRAM_BOT_TOKEN | documented_only | bots/client_bot/config/example.env:23 | docs-only fallback |
| CLIENT_WEBAPP_PORT | optional | none | int | PORT | documented_only | bots/client_bot/README.md:62 | docs-only |

## 6. Route inventory
| method | path | purpose | source |
|---|---|---|---|
| GET | / | root liveness text `OK` | bots/client_bot/main.py:3548-3550 |
| GET | /health | service health json | bots/client_bot/main.py:3426-3429 |
| GET | /service-health | alias of /health | bots/client_bot/main.py:3426-3429 |
| GET | /api/webapp/health | webapp static/config health | bots/client_bot/main.py:3431-3442 |
| GET | /WEBAPP, /WEBAPP/ | uppercase webapp alias index | bots/client_bot/main.py:3371-3377 |
| GET | /assets/webapp.bundle.css, /webapp.css, /app.css | css aliases | bots/client_bot/main.py:3378-3385 |
| GET | /assets/webapp.bundle.js, /webapp.js, /app.js | js aliases | bots/client_bot/main.py:3386-3393 |
| GET | /favicon.ico | suppress favicon errors (204) | bots/client_bot/main.py:3394-3396 |
| GET | /webapp, /webapp/ | legacy redirect/serve | bots/client_bot/main.py:3398-3405 |
| GET | <WEBAPP_PATH>, <WEBAPP_PATH>/ | canonical webapp route | bots/client_bot/main.py:3407-3412 |
| GET | <WEBAPP_PATH>/config.json | runtime config for webapp | bots/client_bot/main.py:3414-3418 |
| GET | <WEBAPP_PATH>/<path:filename> | static file serving | bots/client_bot/main.py:3420-3424 |
| GET | /api/webapp/lookup | lookup by plate | bots/client_bot/main.py:3444-3456 |
| POST | /api/webapp/session | validate initData and mint session token | bots/client_bot/main.py:3458-3481 |
| POST | /api/webapp/submit | submit webapp form | bots/client_bot/main.py:3482-3528 |
| POST | /webhook/<path_secret> | Telegram webhook receiver | bots/client_bot/main.py:3530-3540 |

## 7. Deploy/dependency audit
- Dockerfile: python 3.11-slim, `pip install -r requirements.txt`, `CMD ["python", "main.py"]`.
- Python dependencies: `requirements.txt` == `bots/client_bot/requirements.txt`.
- Node: `package.json` отсутствует; только `index.js` launcher.
- GitHub Actions: `.github/workflows/tests.yml` выполняет unit tests на Python 3.11.
- BotHost config: `.bothost/entrypoint.conf` (`main_file=main.py`).
- Shell scripts: отсутствуют.

## 8. Risk analysis
1. Runtime ambiguity: Python entrypoint + Node launcher + platform configs.
2. Env ambiguity: много fallback/legacy ключей.
3. Webhook prerequisites strictness: нужен валидный public base + secret.
4. Doc/code drift: часть env заявлена в docs, но не читается кодом.
5. Polling/webhook operational conflict risk (409 handling + webhook state).
6. Multi-storage complexity (files + optional db + optional github sync + registry).

## 9. What is likely blocking stable deployment
- Наиболее вероятные блокеры:
  - не задан токен;
  - выбран webhook mode без корректного base URL;
  - отсутствует `BOT_PATH_SECRET`;
  - платформа запускает неожиданный entrypoint.
- Runtime selection определяется: Docker CMD, `.bothost/entrypoint.conf`, наличием `index.js`.
- Webhook зависит от URL chain (`WEBHOOK_URL` -> `PUBLIC_BASE_URL` -> `DOMAIN`) и секрета.
- Webapp зависит от `CLIENT_WEBAPP_ENABLED`, `WEBAPP_PATH`, наличия статических файлов.

## 10. Minimal required env for first successful launch
- Минимум для старта процесса: один валидный token (`CLIENT_TELEGRAM_BOT_TOKEN` или alias).
- Минимум для webhook-старта:
  1) token,
  2) `BOT_PATH_SECRET`,
  3) `WEBHOOK_URL` или `PUBLIC_BASE_URL` или `DOMAIN`.

## 11. Local validation checklist
1. `pip install -r requirements.txt`.
2. `python -m unittest discover -s tests -p "test_*.py"`.
3. Запуск `python main.py` с нужным env.
4. Проверить `/health`, `/WEBAPP`, `/WEBAPP/config.json`.
5. Проверить логи mode/source.

## 12. Post-deploy validation checklist
1. `/health` возвращает 200 и `status=ok`.
2. WebApp маршруты и ассеты доступны.
3. Webhook endpoint отвечает 200.
4. `getWebhookInfo` показывает ожидаемый URL.
5. В логах есть mode/token_source/base_url_source/env counters.

## 13. Source references
- `main.py:1-9`
- `services/client_bot_service/app/main.py:1-5`
- `services/client_bot_service/app/config.py:5-126`
- `bots/client_bot/main.py:260-313,626-677,3365-3553,9037-9260`
- `bots/client_bot/services/ai_service.py:54-61,81-88`
- `bots/client_bot/services/telegram_api.py:24-43`
- `bots/client_bot/services/outgoing_queue.py:69-70`
- `bots/client_bot/storage.py:59-63,120-128`
- `shared/clients_registry.py:14,23-27`
- `Dockerfile:1-13`, `.bothost/entrypoint.conf:1-2`, `.github/workflows/tests.yml:1-22`
- `README.md:1-117`, `bots/client_bot/README.md:1-89`, `bots/client_bot/config/example.env:1-48`
