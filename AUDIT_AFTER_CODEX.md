# AUDIT_AFTER_CODEX

## 1) Что было не так

1. BotHost мог авто-детектить Node/JS и пытаться запускать webapp frontend как server entrypoint (`window is not defined`).
2. Поллинг мог конфликтовать с активным webhook и не получать апдейты стабильно.
3. Токен client-bot мог браться из fallback chain без явного opt-in.
4. WebApp статика имела риск срабатывания на имя `app.js`.
5. В репозитории были legacy-артефакты (`railway.toml`, `Procfile`, `run_all.sh`) мешающие предсказуемому BotHost деплою.

## 2) Что изменено

### 2.1 BotHost hardening
- Добавлен корневой `Dockerfile` (python-only, `CMD ["python", "main.py"]`).
- Legacy деплой-артефакты перенесены в `legacy/`:
  - `legacy/railway.toml`
  - `legacy/Procfile`
  - `legacy/run_all.sh`

### 2.2 WebApp static hardening
- Переименованы реальные фронтовые файлы:
  - `services/client_bot_service/app/webapp/app.js` → `webapp.js`
  - `services/client_bot_service/app/webapp/app.css` → `webapp.css`
- Обновлен `index.html` на новые пути `/webapp.js` и `/webapp.css`.
- В backend оставлены алиасы совместимости:
  - `/app.js` → отдаёт `webapp.js`
  - `/app.css` → отдаёт `webapp.css`
- Обновлена webapp health проверка на новые имена файлов.

### 2.3 Polling/Webhook стабилизация
- В polling режиме на старте вызывается `deleteWebhook(drop_pending_updates=True)` и логируется `mode=polling` + `polling started`.
- Webhook не включается автоматически: при `CLIENT_BOT_MODE=webhook` без `WEBHOOK_URL` пишется warning и используется polling fallback.
- Сохранился защитный цикл polling с retry и обработкой исключений.

### 2.4 ENV/token изоляция client-bot
- Введён opt-in для fallback токенов:
  - `ALLOW_TOKEN_FALLBACK=1` включает fallback chain (`TELEGRAM_BOT_TOKEN`, `BOT_API_TOKEN`, `API_TOKEN`, `BOT_TOKEN`, `TOKEN`).
  - По умолчанию используется только `CLIENT_TELEGRAM_BOT_TOKEN`.
- Аналогично исправлено в:
  - `services/client_bot_service/app/config.py`
  - `bots/client_bot/main.py`
- Startup лог дополнен: `effective_bot=client` + `token_source=...`.

### 2.5 Очередь постов client-bot
- В client-bot снова запускается `posts_queue_worker` (файловое хранилище `data/posts_queue.json`), функционал не вынесен в reviews-bot.

### 2.6 URL/Storage observability
- Лог старта расширен по режимам:
  - `effective_bot=client`
  - `mode=...`
  - `token_source=...`
  - `storage_mode=db|files`
- `build_webapp_config()` теперь дополнительно возвращает `webappUrl` и `baseUrl`.

## 3) Изменённые файлы

- `Dockerfile`
- `bots/client_bot/main.py`
- `services/client_bot_service/app/config.py`
- `services/client_bot_service/app/webapp/index.html`
- `services/client_bot_service/app/webapp/webapp.js`
- `services/client_bot_service/app/webapp/webapp.css`
- `tests/test_bothost_contract.py`
- `tests/test_webapp_static.py`
- `tests/test_client_webapp_static_routes.py`
- `tests/test_webapp_routes.py`
- `tests/test_polling_webhook_mode.py`
- `README_AFTER_DEPLOY.md`
- `AUDIT_AFTER_CODEX.md`
- `legacy/railway.toml`
- `legacy/Procfile`
- `legacy/run_all.sh`

## 4) Добавленные/обновленные тесты

1. `tests/test_bothost_contract.py`
   - проверяет Dockerfile python-entrypoint и отсутствие node-команд;
   - проверяет приоритет портов `PORT -> CLIENT_SERVICE_PORT -> 8000`;
   - проверяет token fallback только при `ALLOW_TOKEN_FALLBACK=1`.

2. `tests/test_webapp_static.py`, `tests/test_client_webapp_static_routes.py`, `tests/test_webapp_routes.py`
   - проверяют 200 для `/WEBAPP`, `/app.js`, `/webapp.js`, `/app.css`, `/webapp.css`, `/WEBAPP/config.json`.

3. `tests/test_polling_webhook_mode.py`
   - проверяет, что в polling режиме вызывается `delete_webhook(..., drop_pending_updates=True)`.

## 5) Текущая архитектура (кратко)

- `main.py` — единый root entrypoint (логирует старт и вызывает только client service).
- `services/client_bot_service/app/main.py` — сервисная инициализация Flask + запуск background polling.
- `bots/client_bot/main.py` — основная бизнес-логика, routing, webapp API/static, polling loop.
- `services/client_bot_service/app/webapp/` — фронтовая статика (`index.html`, `webapp.js`, `webapp.css`, `config.json`).
- `legacy/` — изолированные старые деплой файлы.

## 6) Known limitations

1. Режим `CLIENT_BOT_MODE=webhook` оставлен как future-compatible, но текущий runtime всё равно переключается на polling (с warning в логах).
2. В unit-тестах возможны `ResourceWarning` от старых тестов/Flask response cleanup (не влияет на pass/fail).
3. Для полноценной валидации "Bot отвечает /start и /help" нужен реальный деплой на BotHost с рабочим Telegram токеном (локально это не эмулируется unit-тестом).
