# README_AFTER_DEPLOY

## BotHost запуск (client-bot)

### Правильный entrypoint
- Главный файл в корне: `main.py`.
- Он запускает только Python service client-bot: `services.client_bot_service.app.main:main`.
- Node/WebApp файлы (`app.js`) не являются entrypoint.

### Команда запуска
- `python main.py`

## Порт и host
- Единая логика порта:
  - `PORT` (приоритет)
  - `CLIENT_SERVICE_PORT` (fallback)
  - `8000` (default)
- Host: `CLIENT_SERVICE_HOST` (default `0.0.0.0`).

## Токен client-bot (fallback chain)
1. `CLIENT_TELEGRAM_BOT_TOKEN`
2. `TELEGRAM_BOT_TOKEN`
3. `BOT_API_TOKEN`
4. `API_TOKEN`

Если токен не найден — приложение падает с `RuntimeError` и понятным сообщением.

## Режим запуска
- `CLIENT_BOT_MODE`:
  - default: `polling`
  - `webhook` не включается автоматически без явного значения.
- На старте логируются: `mode`, `domain`, `webapp_url`, `port`, `token_source` (без токена).

## WebApp URL / DOMAIN
Поддерживаемые переменные:
1. `CLIENT_WEBAPP_URL`
2. `WEBAPP_URL`
3. Если обе пусты: строится `https://{DOMAIN}{WEBAPP_PATH}`

Правила:
- `DOMAIN` очищается до хоста (без схемы и `/`).
- URL нормализуется в HTTPS.
- `WEBAPP_PATH` по умолчанию `/WEBAPP`.

## WebApp маршруты
- `/WEBAPP` и `/WEBAPP/` → `index.html`
- `/app.js`, `/app.css` → статика
- `/api/webapp/session`
- `/api/webapp/submit`

`/api/webapp/submit`:
- приоритет `session_token`, fallback `initData`
- ошибки: `invalid_init_data`, `session_expired`, `phone_required`

## Мастер-чат
Для `CLIENT_MASTERS_CHAT_ID`:
- обычный текст без команд не создаёт тикеты;
- работают команды и callback-кнопки;
- поддержаны `/tickets`, `/new`, `/waiting`, `/inprogress`, `/ticket <id>`.

## Картотека клиентов
- Единый файл: `./clients.jsonl` (в корне репозитория).
- Клиент upsert при обращениях через приватный чат.
- Нормализация телефонов в формат `+7XXXXXXXXXX`.

## Storage mode
- Если задан `DATABASE_URL`/`POSTGRES_URL`/`POSTGRESQL_URL` — включается DB-слой.
- Если БД не задана — файловый режим (`data/*.json`, `clients.jsonl`).

## ENV contract (client-bot)

### Required
- `CLIENT_TELEGRAM_BOT_TOKEN` (или fallback chain выше)
- `PORT` (или `CLIENT_SERVICE_PORT`)
- `CLIENT_MASTERS_CHAT_ID`
- `CLIENT_MASTER_USER_IDS`
- `DOMAIN` (рекомендуется как обязательный для WebApp/public URL)

### Recommended
- `CLIENT_NOTIFY_MODE` (default `dm_then_chat`)
- `BOT_PATH_SECRET`
- `DATABASE_URL`
- `TIMEZONE`

### Optional / legacy-compatible
- `CLIENT_MASTER_CHAT_ID` (legacy alias)
- `CLIENT_MASTER_IDS` (legacy alias)
- `WEBAPP_URL` (fallback)
- `CLIENT_CHAT_ID` (fallback masters chat)
- `CLIENT_RUN_MODE`/`RUN_MODE` (legacy mode aliases)

## Smoke
- `python -m unittest discover -s tests -p 'test_*.py'`
