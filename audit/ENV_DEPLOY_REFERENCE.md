# ENV deploy reference (runtime, фактически читаемые в коде)

## Обязательные для production
- `TELEGRAM_CLIENT_BOT_TOKEN` — токен client_bot, используется для отправки сообщений клиентам и /start клавиатуры. Чтение: `src/infrastructure/config/index.js`, `app.js`.
- `TELEGRAM_MASTER_BOT_TOKEN` — токен master_bot, используется для ответов мастерам/инлайн-кнопок/дублей в чат мастеров. Чтение: `src/infrastructure/config/index.js`, `src/interfaces/master_bot/index.js`, `src/server/index.js`.
- `TELEGRAM_INTEGRATION_BOT_TOKEN` — токен integration_bot webhook-интерфейса. Чтение: `src/infrastructure/config/index.js`.
- `MASTER_BOT_ADMIN_IDS` — список Telegram ID админов через запятую; только они получают admin автоматически. Чтение: `src/infrastructure/config/index.js`, `src/core/application/masterService.js`, `src/interfaces/master_bot/index.js`.
- `WEBAPP_URL` — URL WebApp для кнопки в client_bot. Чтение: `src/infrastructure/config/index.js`, `src/interfaces/client_bot/index.js`.

## Рекомендуемые
- `TELEGRAM_MASTERS_CHAT_ID` — chat id общего чата мастеров для дублирования новых заявок и интерактивных действий. Чтение: `src/infrastructure/config/index.js`, `src/server/index.js`.
- `WEBAPP_TELEGRAM_CHANNEL_LINK` — ссылка на Telegram-канал на экране результата WebApp. Чтение: `src/infrastructure/config/index.js`, инъекция в `src/server/index.js`, использование в `public/webapp.js`.
- `WEBAPP_DEDUPE_WINDOW_MS` — окно серверной дедупликации идентичных WebApp-заявок. Чтение: `src/infrastructure/config/index.js`, `src/server/index.js`. Default: `45000`.
- `DB_FILE_PATH` — путь к json-хранилищу. Чтение: `src/infrastructure/db/index.js`.

## Optional (имеют безопасные default)
- `PORT` (default `3000`)
- `NODE_ENV` (default `development`)
- `DB_URL` (документированный placeholder, default `postgres://localhost:5432/telegram_reviews`)
- `QUEUE_DRIVER` (default `memory`)
- `ONE_C_WEBHOOK_SECRET` (default empty)
- `ENABLE_INTEGRATION_WORKER` (default `true`)
- `INTEGRATION_RETRY_MAX` (default `3`)
- `INTEGRATION_RETRY_DELAY_SECONDS` (default `60`)
- `ONE_C_SYNC_ENABLED` (default `false`)
- `EMAIL_IMPORT_ENABLED` (default `true`)
- `FEEDBACK_REQUEST_DELAY_MINUTES` (default `5`)
- `SCHEDULER_INTERVAL_MS` (default `15000`)
- `SCHEDULER_BATCH_SIZE` (default `10`)
- `SCHEDULER_MAX_ATTEMPTS` (default `3`)
- `SCHEDULER_STUCK_TIMEOUT_MS` (default `300000`)

## Legacy / documented-only
- `DB_URL` — сейчас не используется как активное подключение (платформа работает на JSON-store), но остаётся в конфиге для контрактной совместимости.
