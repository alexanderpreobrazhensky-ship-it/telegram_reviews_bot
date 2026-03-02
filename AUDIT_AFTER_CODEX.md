# AUDIT_AFTER_CODEX

## 1. Краткий итог
Стабилизирован Python-only запуск client-bot для BotHost, добавлен fallback-скрипт запуска, WebApp статика переведена на безопасные bundle-имена с алиасами совместимости, усилен webhook->polling fallback при невалидном URL, и расширены smoke/contract тесты.

## 2. Изменённые файлы
- `bots/client_bot/main.py`
- `bots/client_bot/webapp/index.html`
- `bots/client_bot/webapp/assets/webapp.bundle.js`
- `bots/client_bot/webapp/assets/webapp.bundle.css`
- `services/client_bot_service/app/webapp/index.html`
- `services/client_bot_service/app/webapp/assets/webapp.bundle.js`
- `services/client_bot_service/app/webapp/assets/webapp.bundle.css`
- `tests/test_bothost_contract.py`
- `tests/test_polling_webhook_mode.py`
- `tests/test_webapp_static.py`
- `tests/test_client_webapp_static_routes.py`
- `start.sh`
- `README_AFTER_DEPLOY.md`
- `AUDIT_AFTER_CODEX.md`

## 3. Что именно сделано

### 3.1 BotHost entrypoint hardening
- Сохранён root entrypoint `main.py` (Python).
- Сохранён `Dockerfile` с `CMD ["python", "main.py"]`.
- Добавлен `start.sh` (`exec python main.py`) как fallback для тарифов без Dockerfile.
- Тестом зафиксировано отсутствие типичных Node-entrypoint маркеров в корне.

### 3.2 Polling/Webhook
- В `CLIENT_BOT_MODE=webhook` теперь проверяется валидность `WEBHOOK_URL` (только корректный `https://...`).
- При missing/invalid URL пишется warning и выполняется polling fallback.
- В polling сохраняется `deleteWebhook(drop_pending_updates=True)` + `polling started`.

### 3.3 WebApp static hardening
- Физическая статика перенесена на пути:
  - `assets/webapp.bundle.js`
  - `assets/webapp.bundle.css`
- `index.html` обновлён на новые bundle-пути.
- Сохранены алиасы обратной совместимости `/app.js`, `/app.css`.
- Добавлены маршруты `/assets/webapp.bundle.js` и `/assets/webapp.bundle.css`.

## 4. Реально читаемые env (client-bot, алфавитно)
`ALLOW_TOKEN_FALLBACK`, `API_TOKEN`, `AUTO_PIN_ON_DEPLOY`, `AUTO_PIN_ON_START`, `BOT_API_TOKEN`, `BOT_PATH_SECRET`, `BOT_TOKEN`, `CLIENT_ACTIVE_TICKET_TTL_HOURS`, `CLIENT_AUTO_PIN_ON_DEPLOY`, `CLIENT_AUTO_PIN_ON_START`, `CLIENT_BOT_MODE`, `CLIENT_CHAT_ID`, `CLIENT_DATA_DIR`, `CLIENT_MASTER_CHAT_ID`, `CLIENT_MASTER_CHAT_MODE`, `CLIENT_MASTER_IDS`, `CLIENT_MASTER_USER_IDS`, `CLIENT_MASTERS_CHAT_ID`, `CLIENT_NOTIFY_MODE`, `CLIENT_RUN_MODE`, `CLIENT_SERVICE_HOST`, `CLIENT_SERVICE_PORT`, `CLIENT_SHOW_REGLAMENT_PHRASE`, `CLIENT_TELEGRAM_BOT_TOKEN`, `CLIENT_WEBAPP_ENABLED`, `CLIENT_WEBAPP_INITDATA_MAX_AGE_SECONDS`, `CLIENT_WEBAPP_SESSION_SECRET`, `CLIENT_WEBAPP_URL`, `DATABASE_URL`, `DB_ENABLED`, `DEEPSEEK_API_KEY`, `DEEPSEEK_MODEL`, `DOMAIN`, `GEMINI_API_KEY`, `LIRA_ADDRESS`, `LIRA_MAP_URL`, `LIRA_PHONE`, `MASTER_CHAT_MODE`, `OPENAI_API_KEY`, `PORT`, `POSTGRESQL_URL`, `POSTGRES_URL`, `RUN_MODE`, `SHOW_REGLAMENT_PHRASE`, `SHOW_ROUTE_IMAGE`, `TELEGRAM_BOT_TOKEN`, `TIMEZONE`, `TOKEN`, `WEBAPP_ENABLED`, `WEBAPP_PATH`, `WEBAPP_URL`, `WEBHOOK_URL`.

## 5. Ручной чек-лист на BotHost
1. Включить Dockerfile (если доступно).
2. Если Dockerfile недоступен: главный файл `main.py`, команда `bash start.sh`.
3. Проверить env: `CLIENT_TELEGRAM_BOT_TOKEN`, `CLIENT_BOT_MODE=polling`, `PORT`, `DOMAIN`.
4. Проверить логи старта: `effective_bot=client`, `mode=polling`, `deleteWebhook ok`, `polling started`.
5. Проверить HTTP: `/health`, `/WEBAPP`, `/WEBAPP/config.json`, `/assets/webapp.bundle.js`, `/app.js`, `/app.css`.

## 6. Ограничения
- Полноценная валидация Telegram-ответов (`/start`, `/help`) требует реального деплоя с валидным токеном.
- В репозитории остаются исторические тесты старого `main.py` (reviews legacy), которые не относятся к новому client entrypoint контракту.
