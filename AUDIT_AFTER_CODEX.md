# AUDIT_AFTER_CODEX (подробный отчёт)

## 1) Ключевая цель и итог
Репозиторий приведён к стабильному запуску на BotHost через связку **Node bootstrap (`index.js`) → Python (`main.py`)**. Автодетект платформы больше не влияет на запуск python-процесса.

## 2) Ключевое дерево проекта (актуальное)
- `index.js` — BotHost entrypoint (spawn python main.py)
- `main.py` — root python entrypoint (только client-bot service)
- `services/client_bot_service/app/main.py` — сервисный старт Flask + режим webhook/polling
- `services/client_bot_service/app/config.py` — нормализация env, URL, токена, порта
- `bots/client_bot/main.py` — Telegram логика, webhook endpoint, WebApp/static маршруты, workers
- `bots/client_bot/webapp/`
  - `index.html`
  - `assets/webapp.bundle.js`
  - `assets/webapp.bundle.css`
  - `config.json`
- `tests/` — контрактные и smoke-тесты

## 3) Entry points и bootstrap
### `index.js`
- запускает `python main.py`
- наследует env
- наследует stdio
- пробрасывает SIGTERM/SIGINT
- корректно завершает процесс при exit дочернего python

### `main.py`
- логирует `client-bot starting (root main.py)`
- запускает только `services.client_bot_service.app.main:main`

## 4) Webhook-first и fallback
### Default mode
- `CLIENT_BOT_MODE` default: `webhook`

### Base URL приоритет
1. `WEBHOOK_URL`
2. `PUBLIC_BASE_URL`
3. `DOMAIN` (нормализуется к `https://...`)

### URL паттерн
- `<base>/webhook/<BOT_PATH_SECRET>`

### Старт webhook
- `BOT_PATH_SECRET` обязателен (иначе RuntimeError)
- выполняется `deleteWebhook(drop_pending_updates=True)`
- выполняется `setWebhook(url=...)`
- Flask слушает `0.0.0.0:$PORT` (или `CLIENT_SERVICE_HOST`)

### Fallback в polling
Если base URL собрать нельзя в режиме webhook:
- лог warning
- переход в polling
- перед polling обязательно `deleteWebhook(drop_pending_updates=True)`

## 5) Webhook handler
- `POST /webhook/<BOT_PATH_SECRET>`
- быстрый ответ `200 OK`
- секрет сравнивается с `BOT_PATH_SECRET`
- без полного дампа апдейта в логах (PII-safe)

## 6) WebApp static hardening
Каноническая runtime-папка:
- `bots/client_bot/webapp/`

Поддерживаемые URL:
- `/WEBAPP`, `/WEBAPP/`
- `/assets/webapp.bundle.js`
- `/assets/webapp.bundle.css`
- `/app.js` (alias)
- `/app.css` (alias)
- `/WEBAPP/config.json`

Дополнительно:
- `Cache-Control` для статики: `no-cache, no-store, must-revalidate, max-age=0`
- `index.html` ссылается только на `/assets/webapp.bundle.js` и `/assets/webapp.bundle.css`

## 7) Удаления и очистка
- удалена дублирующая папка `services/client_bot_service/app/webapp/` (runtime источник теперь один)
- в root не осталось конфликтных node-entrypoint файлов (`package.json`, `app.js`, `server.js`, `main.js` и т.д.)
- оставлен только разрешённый bootstrap `index.js`

## 8) ENV аудит: read / alias / ignored
Ниже карта для аудита (что реально читается кодом).

### Token resolution
- Primary: `CLIENT_TELEGRAM_BOT_TOKEN`
- Fallback (только если primary пуст):
  - `TELEGRAM_BOT_TOKEN`
  - `BOT_API_TOKEN`
  - `API_TOKEN`
  - `BOT_TOKEN`
  - `TOKEN`
- Логируется `token_source`.

### Port/host
- `PORT` → `CLIENT_SERVICE_PORT` → `8000`
- host: `CLIENT_SERVICE_HOST` (default `0.0.0.0`)

### Webhook URL
- base: `WEBHOOK_URL` → `PUBLIC_BASE_URL` → `DOMAIN`
- path: `/webhook/<BOT_PATH_SECRET>`

### Masters/admin compatibility
- primary chat: `CLIENT_MASTERS_CHAT_ID`
- aliases: `CLIENT_CHAT_ID`, `CLIENT_MASTER_CHAT_ID`
- primary users: `CLIENT_MASTER_USER_IDS`
- alias: `CLIENT_MASTER_IDS`
- совместимые списки: `CLIENT_ADMIN_IDS`, `SUPERADMIN_ID`, `REPORT_CHAT_IDS`

### Ignored / неиспользуемые напрямую в текущем runtime
- Любые env, не перечисленные в маппинге выше и не читаемые в `services/client_bot_service/app/config.py` или `bots/client_bot/main.py`, считаются ignored и безопасно игнорируются.

## 9) Очередь постов (client-bot)
- хранение: `data/posts_queue.json`
- worker: стартует вместе с client-bot (`posts_queue_worker`)
- инициализация файла: `ensure_posts_queue_file(...)`
- функционал не зависит от внешних сервисов

## 10) Чеклист «бот не отвечает»
1. Проверить `CLIENT_TELEGRAM_BOT_TOKEN`.
2. Проверить `CLIENT_BOT_MODE=webhook`.
3. Проверить `BOT_PATH_SECRET`.
4. Проверить `WEBHOOK_URL` или `PUBLIC_BASE_URL`/`DOMAIN`.
5. Проверить, что сервис слушает `0.0.0.0:$PORT`.
6. Проверить `/health` (200).
7. Проверить логи: `mode=webhook`, `deleteWebhook ok`, `setWebhook ok`.

## 11) Инструкция getWebhookInfo
1. Выполнить:
   - `https://api.telegram.org/bot<TOKEN>/getWebhookInfo`
2. Проверить:
   - `url` совпадает с `https://<base>/webhook/<secret>`
   - `pending_update_count` не растёт
   - `last_error_message` пустой

## 12) Что изменено по файлам
- Добавлен `index.js` bootstrap.
- Упрощён root `main.py` для запуска только client-bot service.
- Обновлён `services/client_bot_service/app/config.py` (token policy, URL source resolver).
- Обновлён `services/client_bot_service/app/main.py` (webhook-first логирование, fallback).
- Обновлён `bots/client_bot/main.py` (webhook URL source priority, static cache-control, polling fallback).
- Обновлены тесты контрактов BotHost/webhook/static и no-node файлов.
- Удалён дубликат webapp статики из service-папки.
- Обновлены `README_AFTER_DEPLOY.md` и `requirements.txt`.
