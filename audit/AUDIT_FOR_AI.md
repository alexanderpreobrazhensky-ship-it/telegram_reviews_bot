# Repository Audit for AI (read-only analysis)

## 1) Краткое описание проекта
- Репозиторий реализует **client-bot** для Telegram на Python (Flask + polling/webhook), с Dockerfile-first запуском на Python (`python main.py`).
- Основной исполняемый путь: `main.py` -> `services/client_bot_service/app/main.py` -> `bots/client_bot/main.py`.
- В коде зафиксировано, что поддерживается только client-bot сервис. См. `README.md` и root-entrypoints.

## 2) Snapshot структуры репозитория
- `main.py` — root Python entrypoint.
- `index.js` — legacy bootstrap (не production-путь).
- `services/client_bot_service/app/` — thin wrapper-конфиг/entrypoint сервиса.
- `bots/client_bot/` — основная бизнес-логика бота, Flask routes, webhook/polling, storage, telegram API, AI-интеграция, webapp static.
- `shared/clients_registry.py` — общий реестр клиентов (jsonl + file lock).
- `tests/` — smoke/unit тесты entrypoints/health/routes/webhook URL.
- `data/` — runtime data (`tickets.jsonl`, `clients.jsonl`, `system.json`).
- `review.html`, `logo.png` — вне основного runtime-кода (по коду прямых импортов/serving-роутов не найдены).

## 3) Точки входа (entrypoints)
### Фактические entrypoints
1. `index.js` (Node): `spawn('python', ['main.py'])`. Используется как main file для BotHost. (index.js:1-30)
2. `main.py` (Python root): вызывает `services.client_bot_service.app.main.main`. (main.py:1-10)
3. `services/client_bot_service/app/main.py`: вызывает `bots.client_bot.main.main`. (services/client_bot_service/app/main.py:1-6)
4. `bots/client_bot/main.py`: финальный runtime (Flask app + polling/webhook loop). (bots/client_bot/main.py:9040-9261)

### Альтернативные/служебные entrypoints
- `start_polling_background()` в `bots/client_bot/main.py` — фоновой поток polling, не root-entrypoint. (bots/client_bot/main.py:9263-9274)

### CI/CD, Docker, workflow
- Обнаружен GitHub Actions workflow: `.github/workflows/tests.yml` (push/pull_request на `main`, setup Python 3.11, `pip install -r requirements.txt`, `unittest`).
- Обнаружен platform-specific конфиг `.bothost/entrypoint.conf` (`main_file=index.js`, `branch=main`).
- В репозитории добавлен root `Dockerfile` с python-only контрактом запуска.

## 4) Фактическая схема запуска
### Local Python
- `python main.py` -> загрузка runtime config -> выбор `webhook`/`polling`.
- По умолчанию mode = `webhook` (если env mode не задан), но при невалидном base URL происходит fallback на polling.

### BotHost
- Документированный сценарий: main file = `index.js`, который запускает Python и пробрасывает сигналы/stdio.

### Webhook режим
- Формируется webhook URL из `WEBHOOK_URL` -> `PUBLIC_BASE_URL` -> `DOMAIN` + `/webhook/<BOT_PATH_SECRET>`.
- При успехе: `deleteWebhook` -> `setWebhook` -> `Flask app.run(host, port)`.

### Polling режим
- Выполняется `deleteWebhook(drop_pending_updates=True)` и далее long polling через Telegram API.

## 5) HTTP/API/WebApp маршруты
Определены в `register_webapp_routes()` и `create_flask_app()`:
- `GET /` — root health-like plain `OK`.
- `GET /health`, `GET /service-health` — статус сервиса.
- `GET /api/webapp/health` — health webapp static+config.
- `GET /WEBAPP`, `/WEBAPP/` — alias webapp index.
- `GET /webapp`, `/webapp/` — legacy redirect/serve.
- `GET <WEBAPP_PATH>`, `<WEBAPP_PATH>/` — основной webapp route (обычно `/WEBAPP`).
- `GET /assets/webapp.bundle.js`, `/webapp.js`, `/app.js` — JS bundle aliases.
- `GET /assets/webapp.bundle.css`, `/webapp.css`, `/app.css` — CSS bundle aliases.
- `GET <WEBAPP_PATH>/config.json` — runtime config для webapp.
- `GET <WEBAPP_PATH>/<path:filename>` — static serving из `bots/client_bot/webapp`.
- `GET /api/webapp/lookup` — поиск авто по plate.
- `POST /api/webapp/session` — валидация `initData`, выдача `session_token`.
- `POST /api/webapp/submit` — отправка webapp формы.
- `POST /webhook/<path_secret>` — Telegram webhook endpoint.

Ссылки: bots/client_bot/main.py:3371-3548.

## 6) ENV audit (runtime-used)
Ниже перечислены переменные, обнаруженные в коде. **Секреты/значения не приводятся**.

### Core runtime / launch
- `CLIENT_TELEGRAM_BOT_TOKEN` (required, secret, string) — основной токен бота.
- `TELEGRAM_BOT_TOKEN`, `BOT_API_TOKEN`, `API_TOKEN`, `BOT_TOKEN`, `TOKEN` (conditional fallback, secret, string) — fallback цепочка токена.
- `CLIENT_BOT_MODE` / `CLIENT_RUN_MODE` / `RUN_MODE` (optional, enum webhook|polling, default webhook) — режим запуска.
- `CLIENT_SERVICE_HOST` (optional, default `0.0.0.0`) — bind host Flask.
- `PORT` / `CLIENT_SERVICE_PORT` (optional, int, default `8000`) — bind port.
- `BOT_PATH_SECRET` (required for secure webhook/webapp session fallback, secret-like string).

### Public URL/WebApp URL resolution
- `WEBHOOK_URL`, `PUBLIC_BASE_URL`, `DOMAIN` (conditional, url/domain) — base URL для webhook.
- `CLIENT_WEBAPP_URL`, `WEBAPP_URL` (optional, url) — публичный URL webapp.
- `WEBAPP_PATH` (optional, default `/WEBAPP`) — путь webapp.
- `CLIENT_WEBAPP_ENABLED` / `WEBAPP_ENABLED` (optional, bool, default enabled).

### WebApp/session
- `CLIENT_WEBAPP_INITDATA_MAX_AGE_SECONDS` (optional, int, default `86400`).
- `CLIENT_WEBAPP_SESSION_SECRET` (optional, secret; fallback to `BOT_PATH_SECRET`).
- `CLIENT_WEBAPP_TEST_MODE` (optional, bool-ish).

### Telegram delivery/retry queue
- `CLIENT_TG_TIMEOUT_SECONDS` (optional, int, default 15).
- `CLIENT_TG_RETRY_MAX` (optional, int, default 5).
- `CLIENT_TG_RETRY_BASE_SLEEP_SECONDS` (optional, int, default 1).
- `CLIENT_TG_QUEUE_ENABLED` (optional, bool-ish, default enabled).

### Masters/admins/chats
- `CLIENT_MASTERS_CHAT_ID`, `CLIENT_CHAT_ID`, `CLIENT_MASTER_CHAT_ID` (optional; chat targets).
- `CLIENT_MASTER_USER_IDS`, `CLIENT_MASTER_IDS` (optional; list of IDs).
- `CLIENT_MASTER_CHAT_MODE`, `MASTER_CHAT_MODE` (optional; mode switch).
- `MASTER_USERNAMES` (optional/legacy-supported in runtime paths).
- `CLIENT_ADMIN_IDS` (optional in code; operationally important).
- `CLIENT_POST_TARGET_ID`, `CLIENT_POST_CHAT_ID` (optional; post targeting).
- `CLIENT_CHANNEL_ID` (optional; channel pinning).
- `CLIENT_NOTIFY_MODE` (optional, default `dm_then_chat`).

### AI behavior
- `CLIENT_DEEPSEEK_API_KEY` (optional, secret; required only if AI enabled).
- `CLIENT_DEEPSEEK_BASE_URL` (optional, url).
- `CLIENT_DEEPSEEK_MODEL` (optional, string).
- `CLIENT_AI_TIMEOUT_SECONDS` (optional, int, default 10).
- `CLIENT_FORCE_FALLBACK`, `FORCE_FALLBACK` (optional, bool-ish).
- `AI_FALLBACK_THRESHOLD` (optional, int, default 3).
- `AI_FALLBACK_TTL_SECONDS` (optional, int, default 1800).
- `AI_FALLBACK_WINDOW_SECONDS` (optional, int, default 600).

### Geo/contact/UI toggles
- `LIRA_PHONE` (optional, string).
- `LIRA_ADDRESS` (optional, default `Удмуртская 10`).
- `LIRA_MAP_URL` (optional, url).
- `ROUTE_URL` (optional, url).
- `SHOW_ROUTE_IMAGE` (optional, bool-ish).
- `PIN_TEMPLATE_VERSION` (optional, default `v1`).
- `CLIENT_SHOW_REGLAMENT_PHRASE`, `SHOW_REGLAMENT_PHRASE` (optional, bool-ish).
- `CLIENT_AUTO_PIN_ON_START`, `CLIENT_AUTO_PIN_ON_DEPLOY`, `AUTO_PIN_ON_DEPLOY`, `AUTO_PIN_ON_START` (optional, bool-ish).

### Timezone / identity
- `TIMEZONE` (optional, default `Europe/Moscow`).
- `CLIENT_BOT_USERNAME`, `TELEGRAM_BOT_USERNAME`, `BOT_USERNAME` (optional; bot username resolution).

### Storage / persistence / registry / external
- `CLIENT_GITHUB_TOKEN`, `GITHUB_TOKEN` (optional, secret) — GitHub content sync.
- `CLIENT_GITHUB_REPO`, `GITHUB_REPO` (optional, `owner/repo`).
- `CLIENT_GITHUB_BRANCH`, `GITHUB_BRANCH` (optional, default `main`).
- `CLIENTS_REGISTRY_PATH` (optional, file path override).
- `CLIENTS_REGISTRY_LOCK_TIMEOUT_SECONDS` (optional, float, default 5).
- `DATABASE_URL`, `POSTGRES_URL`, `POSTGRESQL_URL` (optional, db url candidates).

### Legacy / compatibility env recognized by config layer
- `REPORT_CHAT_IDS`, `SUPERADMIN_ID`, `MASTER_USERNAMES`, `REMINDER_USERNAMES` — учитываются как legacy-recognized/env telemetry.

## 7) Файлы/конфиги, влияющие на деплой и runtime
- `index.js` — автодетект Node platform / запуск Python.
- `main.py` — Python root entry.
- `services/client_bot_service/app/config.py` — runtime mode/port/token/base-url selection.
- `bots/client_bot/main.py` — главный runtime workflow.
- `requirements.txt`, `bots/client_bot/requirements.txt` — зависимости.
- `README.md` — deploy-инструкции (BotHost/ENV).
- `.github/workflows/tests.yml` — CI-проверки.
- `.bothost/entrypoint.conf` — BotHost main file/branch конфиг.

Отсутствуют: `Dockerfile`, `docker-compose` (но GH Actions workflow присутствует).

## 8) Подозрительно неиспользуемые/вспомогательные артефакты (без удаления)
- `review.html` — не найден в маршрутах/entrypoints.
- `logo.png` — не найден в serving/import paths приложения.
- `bots/client_bot/config/example.env` — шаблон документации, не runtime import.
- `bots/client_bot/config/dictionary_rules.json` — используется через сервис правил (вспомогательный runtime-конфиг).

## 9) Риски и потенциальные причины нестабильного деплоя
1. **Двойной runtime-контур (Node+Python)**: BotHost запускает Node, Node запускает Python; проблемы с Python binary/path могут ломать старт.
2. **Конфликт mode defaults**: дефолт `webhook`, но часть документации/чеклистов ориентирована на polling.
3. **Широкий набор env alias/legacy keys**: высок риск неконсистентной конфигурации.
4. **Отсутствие Dockerfile/workflow в репо**: деплой зависит от внешней платформенной магии и ручных настроек.
5. **Параллельные storage-механизмы** (локальные json/jsonl + optional GitHub sync + registry path override) могут расходиться.
6. **Возможный автодетект Node вместо Python**: наличие `index.js` в корне делает Node primary entry на некоторых платформах.

## 10) Локальный чеклист проверки
1. Установить deps: `pip install -r requirements.txt`.
2. Запустить тесты: `python -m unittest discover -s tests -p "test_*.py"`.
3. Проверить `/health`, `/WEBAPP`, `/api/webapp/health`.
4. Проверить, что webhook URL корректно строится при заданном `BOT_PATH_SECRET`.
5. Проверить fallback в polling при отсутствии `WEBHOOK_URL/PUBLIC_BASE_URL/DOMAIN`.

## 11) Чеклист после деплоя
1. Старт через `index.js` (BotHost), без падений child python.
2. `/health` возвращает `status=ok`.
3. `POST /webhook/<secret>` отвечает 200 при валидном секрете.
4. WebApp routes доступны (`/WEBAPP`, assets, `/WEBAPP/config.json`).
5. Логи подтверждают выбранный mode и source env (`webhook_base_source`, token source).
6. При включённом AI — успешный ping/ответы; при выключенном — контролируемый fallback.

## 12) Источники (path:line)
- README: `README.md:1-70`
- CI/workflow: `.github/workflows/tests.yml:1-19`
- BotHost config: `.bothost/entrypoint.conf:1-2`
- Entrypoints: `index.js:1-30`, `main.py:1-10`, `services/client_bot_service/app/main.py:1-6`
- Runtime config/env aliases: `services/client_bot_service/app/config.py:1-119`
- Основной runtime + routes + webhook/polling: `bots/client_bot/main.py:260-320`, `bots/client_bot/main.py:653-709`, `bots/client_bot/main.py:3371-3548`, `bots/client_bot/main.py:9040-9277`
- Telegram retry/env: `bots/client_bot/services/telegram_api.py:1-45`
- Queue env: `bots/client_bot/services/outgoing_queue.py:66-72`
- AI env: `bots/client_bot/services/ai_service.py:47-95`
- Registry env/path: `shared/clients_registry.py:14-27`
- Storage GitHub sync env: `bots/client_bot/storage.py:57-63`
