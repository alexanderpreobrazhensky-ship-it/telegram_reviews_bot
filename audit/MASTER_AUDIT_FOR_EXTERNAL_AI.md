# MASTER AUDIT FOR EXTERNAL AI

## 1. Executive summary
- Проект — Python Telegram client-bot с Flask HTTP-обвязкой, WebApp-статикой и webhook/polling рантаймом.
- Основная фактическая цепочка запуска: `main.py` → `services/client_bot_service/app/main.py` → `bots/client_bot/main.py`.
- В репозитории есть Node `index.js`, но он только проксирует запуск в Python (`spawn('python', ['main.py'])`).
- Текущее состояние: репозиторий уже содержит audit-артефакты и тесты; production-контракт документирован как Dockerfile-first.
- Главные риски: неоднозначность документации (polling vs webhook), множественные entrypoints (Python + Node wrapper), широкие alias-цепочки env, смешение legacy/runtime переменных.

## 2. Repository snapshot
- Branch: `work`
- Commit: `fa6d084739097b1b146faeec7b331604fdb66724`
- Полный tracked-manifest: `audit/REPO_MANIFEST.txt`

Ключевая структура:
- `main.py` — root entrypoint.
- `services/client_bot_service/app/*` — runtime-config + shim.
- `bots/client_bot/main.py` — основной бот-runtime + Flask routes.
- `bots/client_bot/services/*` — AI, Telegram transport, queue.
- `bots/client_bot/storage.py` и `shared/clients_registry.py` — storage/sync.
- `bots/client_bot/webapp/*` — фронтовая статика и config.
- `Dockerfile`, `.bothost/entrypoint.conf`, `.github/workflows/tests.yml` — deploy/CI контур.

## 3. Entrypoints and startup chain
### Entrypoints
1. `main.py` — основной Python entrypoint.
2. `services/client_bot_service/app/main.py` — сервисный shim.
3. `bots/client_bot/main.py` (`main()`) — основной runtime.
4. `index.js` — Node launcher-обёртка.
5. Docker CMD: `python main.py`.
6. BotHost config: `.bothost/entrypoint.conf` (`main_file=main.py`).

### Основной / вспомогательный / legacy
- Основной: `main.py` + Docker CMD.
- Вспомогательный: `services/client_bot_service/app/main.py`.
- Совместимость/альтернатива: `index.js`, `.bothost/entrypoint.conf`.
- Legacy-suspected: наличие одновременно Python-only и Node-обвязки.

### Startup chain (факт)
1. Загрузка runtime env через `load_runtime_config()`.
2. Разрешение run mode (`CLIENT_BOT_MODE`/aliases, default `webhook`).
3. Разрешение token fallback-chain.
4. `webhook` путь: resolve URL (`WEBHOOK_URL`→`PUBLIC_BASE_URL`→`DOMAIN`) + `BOT_PATH_SECRET`, `deleteWebhook`, `setWebhook`, `Flask app.run`.
5. `polling` путь (или fallback): `deleteWebhook` и `poll_updates`.

## 4. Runtime model
- **Python runtime (primary):** Flask + requests + openai + psycopg.
- **Node runtime:** отдельной бизнес-логики нет, только запуск Python-процесса.
- **Docker runtime:** `python:3.11-slim`, install `requirements.txt`, CMD `python main.py`.
- **Webhook vs polling:** default webhook; fallback в polling при невалидной/отсутствующей base URL.
- **Production path (наиболее вероятный):** Dockerfile + Python entrypoint.
- **Неоднозначности:** README в корне webhook-first, а `bots/client_bot/README.md` делает акцент на polling/BotHost-сценарии.

## 5. Full ENV audit
Ниже — consolidated таблица runtime/doc env (без раскрытия секретов).

| ENV_NAME | required? | default | type | aliases | status | used_in | purpose | notes |
|---|---|---|---|---|---|---|---|---|
| CLIENT_TELEGRAM_BOT_TOKEN | required | - | secret | TELEGRAM_BOT_TOKEN, BOT_API_TOKEN, API_TOKEN, BOT_TOKEN, TOKEN | runtime_used | services/client_bot_service/app/config.py:5-12,65-69; bots/client_bot/main.py:9088-9093 | Telegram bot token | Критично для старта |
| CLIENT_BOT_MODE | optional | webhook | string | CLIENT_RUN_MODE, RUN_MODE | runtime_used | services/client_bot_service/app/config.py:14,52-55; bots/client_bot/main.py:259-264 | режим запуска | нормализация к webhook/polling |
| PORT | optional | 8000 | int | CLIENT_SERVICE_PORT | runtime_used | services/client_bot_service/app/config.py:15,75-77 | HTTP port | platform-provided |
| CLIENT_SERVICE_HOST | optional | 0.0.0.0 | string | - | runtime_used | services/client_bot_service/app/config.py:71-74 | bind host | |
| WEBHOOK_URL | conditional | - | url | PUBLIC_BASE_URL, DOMAIN | runtime_used | services/client_bot_service/app/config.py:16; bots/client_bot/main.py:653-678 | webhook base url | webhook path requires BOT_PATH_SECRET |
| PUBLIC_BASE_URL | conditional | - | url | WEBHOOK_URL, DOMAIN | runtime_used | services/client_bot_service/app/config.py:16; bots/client_bot/main.py:656-678 | webhook base url fallback | |
| DOMAIN | conditional | - | url/domain | WEBHOOK_URL, PUBLIC_BASE_URL | runtime_used | services/client_bot_service/app/config.py:16,84-90; bots/client_bot/main.py:285,659-678 | base domain fallback | sanitize/normalize |
| BOT_PATH_SECRET | conditional | - | secret | - | runtime_used | services/client_bot_service/app/config.py:107; bots/client_bot/main.py:666,3278,3533,9104 | webhook path secret / webapp session fallback | обязателен для корректного webhook URL |
| CLIENT_WEBAPP_URL | optional | - | url | WEBAPP_URL | runtime_used | services/client_bot_service/app/config.py:17; bots/client_bot/main.py:300,695,9163 | webapp public url | fallback DOMAIN+WEBAPP_PATH |
| WEBAPP_PATH | optional | /WEBAPP | path | - | runtime_used | services/client_bot_service/app/config.py:18,85-90; bots/client_bot/main.py:286,310-312 | webapp route base | |
| CLIENT_WEBAPP_ENABLED | optional | 1 | bool | WEBAPP_ENABLED | runtime_used | bots/client_bot/main.py:287-292 | toggle webapp routes | |
| CLIENT_WEBAPP_INITDATA_MAX_AGE_SECONDS | optional | 86400 | int | - | runtime_used | bots/client_bot/main.py:299,3468-3479 | initData TTL | |
| CLIENT_WEBAPP_SESSION_SECRET | optional | BOT_PATH_SECRET | secret | BOT_PATH_SECRET | runtime_used | bots/client_bot/main.py:3278 | webapp session sign secret | |
| TIMEZONE | optional | Europe/Moscow | string | - | runtime_used | bots/client_bot/main.py (multiple), storage timestamps | timezone | |
| DATABASE_URL | optional | - | url | POSTGRES_URL, POSTGRESQL_URL | runtime_used | bots/client_bot/main.py:346-355 | DB connection | DB optional behavior |
| CLIENTS_REGISTRY_PATH | optional | repo clients.jsonl | path | - | runtime_used | bots/client_bot/main.py:320; shared/clients_registry.py:23 | registry location | |
| CLIENTS_REGISTRY_LOCK_TIMEOUT_SECONDS | optional | 5 | int/float | - | runtime_used | shared/clients_registry.py:14 | lock timeout | |
| CLIENT_GITHUB_TOKEN/GITHUB_TOKEN | optional | - | secret | each other | runtime_used | bots/client_bot/main.py:4699; bots/client_bot/storage.py:59 | github storage sync | |
| CLIENT_GITHUB_REPO/GITHUB_REPO | optional | - | string | each other | runtime_used | bots/client_bot/main.py:4700; bots/client_bot/storage.py:60 | github storage sync repo | |
| CLIENT_GITHUB_BRANCH/GITHUB_BRANCH | optional | main | string | each other | runtime_used | bots/client_bot/storage.py:61 | github branch | |
| CLIENT_TG_TIMEOUT_SECONDS | optional | 30 | int | - | runtime_used | bots/client_bot/services/telegram_api.py:25 | telegram request timeout | |
| CLIENT_TG_RETRY_MAX | optional | 3 | int | - | runtime_used | bots/client_bot/services/telegram_api.py:32 | telegram retries | |
| CLIENT_TG_RETRY_BASE_SLEEP_SECONDS | optional | 1.0 | float | - | runtime_used | bots/client_bot/services/telegram_api.py:39 | retry backoff | |
| CLIENT_TG_QUEUE_ENABLED | optional | 1 | bool | - | runtime_used | bots/client_bot/services/outgoing_queue.py:70 | outgoing queue toggle | |
| CLIENT_DEEPSEEK_API_KEY | optional | - | secret | documented DEEPSEEK_API_KEY | runtime_used | bots/client_bot/services/ai_service.py:54 | AI key | code не использует fallback из README |
| CLIENT_DEEPSEEK_BASE_URL | optional | - | url | documented DEEPSEEK_BASE_URL | runtime_used | bots/client_bot/services/ai_service.py:55 | AI endpoint | code не использует fallback из README |
| CLIENT_DEEPSEEK_MODEL | optional | - | string | documented DEEPSEEK_MODEL | runtime_used | bots/client_bot/services/ai_service.py:56 | AI model | code не использует fallback из README |
| CLIENT_AI_TIMEOUT_SECONDS | optional | 10 | int | documented AI_TIMEOUT_SECONDS | runtime_used | bots/client_bot/services/ai_service.py:82-88 | AI timeout | docs/code drift |
| CLIENT_FORCE_FALLBACK | optional | 0 | bool | FORCE_FALLBACK | runtime_used | bots/client_bot/services/ai_service.py:58-60 | force AI fallback | |
| MASTER_USERNAMES | optional | - | list | - | runtime_used | bots/client_bot/main.py:1086,1100 | мастера | описано в docs |
| CLIENT_ADMIN_IDS | optional | - | list | - | runtime_used | bots/client_bot/main.py:1506 | админы | |
| CLIENT_REMINDER_MINUTES | documented_only | 30 | int | REMINDER_MINUTES | documented_only | bots/client_bot/README.md, example.env | docs mention | в текущем коде не найден `os.getenv` |
| TELEGRAM_BOT_TOKEN_CLIENT | documented_only | - | secret | CLIENT_TELEGRAM_BOT_TOKEN | documented_only | bots/client_bot/config/example.env:23 | docs fallback token | не используется в runtime |
| CLIENT_MASTER_CHAT_IDS | documented_only | - | list | - | documented_only | bots/client_bot/README.md:31; example.env:20 | docs variable | код использует singular keys |
| CLIENT_WEBAPP_PORT | documented_only | - | int | PORT | documented_only | bots/client_bot/README.md:62 | docs-only | |
| REPORT_CHAT_IDS, SUPERADMIN_ID, REMINDER_USERNAMES | legacy_suspected | - | string/list | - | legacy_suspected | services/client_bot_service/app/config.py:21-27 | legacy recognized keys | учитываются как used/ignored счётчики |

## 6. Route inventory
| method | path | purpose | declared_in |
|---|---|---|---|
| GET | `/` | root liveness | bots/client_bot/main.py:3548-3551 |
| POST | `/webhook/<path_secret>` | Telegram webhook ingest | bots/client_bot/main.py:3530-3542 |
| GET | `/health` | health check | bots/client_bot/main.py:3426-3429 |
| GET | `/service-health` | alias health check | bots/client_bot/main.py:3427-3429 |
| GET | `/api/webapp/health` | webapp health | bots/client_bot/main.py:3431-3442 |
| GET | `/api/webapp/lookup` | lookup helper API | bots/client_bot/main.py:3444-3456 |
| POST | `/api/webapp/session` | create webapp session token | bots/client_bot/main.py:3458-3480 |
| POST | `/api/webapp/submit` | submit webapp form | bots/client_bot/main.py:3482-3528 |
| GET | `/WEBAPP`, `/WEBAPP/` | webapp index | bots/client_bot/main.py:3371-3376 |
| GET | `/webapp`, `/webapp/` | webapp redirect/alias | bots/client_bot/main.py:3398-3405 |
| GET | `/assets/webapp.bundle.css`, `/webapp.css`, `/app.css` | css static | bots/client_bot/main.py:3378-3384 |
| GET | `/assets/webapp.bundle.js`, `/webapp.js`, `/app.js` | js static | bots/client_bot/main.py:3386-3392 |
| GET | `/favicon.ico` | favicon (logo) | bots/client_bot/main.py:3394-3396 |
| GET | `${WEBAPP_PATH}`, `${WEBAPP_PATH}/` | dynamic webapp route base | bots/client_bot/main.py:3407-3412 |
| GET | `${WEBAPP_PATH}/config.json` | webapp config | bots/client_bot/main.py:3414-3418 |
| GET | `${WEBAPP_PATH}/<path:filename>` | webapp static passthrough | bots/client_bot/main.py:3420-3424 |

## 7. Deploy/dependency audit
- `Dockerfile` реально влияет на запуск: python base image, pip install, `CMD ["python", "main.py"]`.
- `.bothost/entrypoint.conf` задаёт `main.py` и branch `main`.
- `.github/workflows/tests.yml` — CI-only: install deps + `unittest`, не деплой.
- `requirements.txt` и `bots/client_bot/requirements.txt` идентичны (дублирование dependency source).
- `index.js` потенциально может стать платформенным entrypoint при Node autodetection, но фактически запускает Python.
- `README.md` влияет на деплой-интерпретацию (Dockerfile-first); `bots/client_bot/README.md` содержит альтернативный operating narrative (polling/BotHost), что создаёт drift.

## 8. Risk analysis
1. **Entrypoint ambiguity:** Python main + Node wrapper + bothost conf.
2. **Docs/code drift:** разные акценты webhook/polling в README-файлах.
3. **Env ambiguity:** длинные alias-chains для токена/режима/url.
4. **Webhook fallback complexity:** при плохом base URL тихий переход в polling.
5. **Legacy env surface:** recognized legacy keys в config и docs-only переменные.
6. **Dependency source duplication:** два одинаковых requirements файла.
7. **Platform autodetection risk:** наличие `index.js` может менять behavior на некоторых платформах.
8. **Storage complexity:** одновременно filesystem JSON/JSONL + optional DB + optional GitHub sync.

## 9. What is likely blocking stable deployment
- Неполный минимальный env (особенно token + webhook base + BOT_PATH_SECRET).
- Непредсказуемый выбор runtime платформой при наличии `index.js`.
- Разные operational assumptions в README vs `bots/client_bot/README.md`.
- Неочевидность активного storage backend (DB/GitHub/file) без явной конфигурационной политики.

## 10. Minimal required env for first successful launch
Вариант A (webhook-first):
- `CLIENT_TELEGRAM_BOT_TOKEN`
- `CLIENT_BOT_MODE=webhook` (или по умолчанию)
- `BOT_PATH_SECRET`
- один из: `WEBHOOK_URL` / `PUBLIC_BASE_URL` / `DOMAIN`
- (опционально platform): `PORT`

Вариант B (polling fallback/forced):
- `CLIENT_TELEGRAM_BOT_TOKEN`
- `CLIENT_BOT_MODE=polling` (или `RUN_MODE=polling`)

## 11. Local validation checklist
1. `pip install -r requirements.txt`
2. Заполнить env (минимум token + режим).
3. Для webhook: добавить `BOT_PATH_SECRET` + base URL.
4. `python main.py`.
5. Проверить HTTP: `/health`, `/service-health`, WebApp static routes.
6. Проверить, что mode в логах соответствует ожидаемому.

## 12. Post-deploy validation checklist
1. Проверка `/health` и `/service-health` по публичному URL.
2. Для webhook: проверить `getWebhookInfo` в Telegram API.
3. Проверить успешную обработку webhook update или polling loop без 409-штормов.
4. Проверить webapp endpoints (`/WEBAPP`, `/api/webapp/session`, `/api/webapp/submit`).
5. Проверить запись storage (файлы/DB/GitHub path, если включено).

## 13. Source references
- Entrypoints: `main.py:1-9`, `services/client_bot_service/app/main.py:1-5`, `index.js:1-31`, `Dockerfile:1-13`, `.bothost/entrypoint.conf:1-2`.
- Runtime/env selector: `services/client_bot_service/app/config.py:5-126`.
- Mode + URL/env resolution: `bots/client_bot/main.py:259-320`, `bots/client_bot/main.py:626-678`, `bots/client_bot/main.py:9134-9268`.
- Webhook operations: `bots/client_bot/main.py:9102-9129`.
- Routes: `bots/client_bot/main.py:3371-3551`.
- AI env: `bots/client_bot/services/ai_service.py:54-88`.
- Telegram transport env: `bots/client_bot/services/telegram_api.py:25-47`.
- Queue env: `bots/client_bot/services/outgoing_queue.py:70`.
- GitHub storage env: `bots/client_bot/storage.py:59-61`.
- Registry env: `shared/clients_registry.py:14-28`.
- Deploy/docs context: `README.md:1-118`, `bots/client_bot/README.md:1-90`, `bots/client_bot/config/example.env:1-48`, `.github/workflows/tests.yml:1-22`.
