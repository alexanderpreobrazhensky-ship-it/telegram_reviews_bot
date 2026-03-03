# AUDIT_AFTER_CODEX

## Что изменено
- Зафиксирован webhook-first контракт для client-bot: default mode=`webhook`, polling только вручную.
- Добавлен единый конфиг-слой `services/client_bot_service/app/config.py` для аудита env и алиасов.
- Добавлен жёсткий контракт webhook path: только `/webhook/<BOT_PATH_SECRET>`.
- Унифицирован расчёт URL:
  - `PUBLIC_BASE_URL` (primary)
  - `DOMAIN` (fallback)
  - принудительный `https://`
- Root entrypoint (`main.py`) и service startup логируют эффективные параметры запуска без секретов.
- WebApp статика закреплена через bundle-пути и алиасы:
  - `/assets/webapp.bundle.js`, `/assets/webapp.bundle.css`
  - `/app.js`, `/app.css`.

## Обязательные ENV (webhook)
- `CLIENT_TELEGRAM_BOT_TOKEN`
- `BOT_PATH_SECRET`
- `PUBLIC_BASE_URL` (или `DOMAIN`)
- `PORT`

## Рекомендуемые/опциональные
- `CLIENT_WEBAPP_URL` / `WEBAPP_URL`
- `WEBAPP_PATH`
- `DATABASE_URL` (алиасы: `POSTGRES_URL`, `POSTGRESQL_URL`)
- `CLIENT_MASTER_USER_IDS` (алиас: `CLIENT_MASTER_IDS`)
- `CLIENT_MASTERS_CHAT_ID` (алиасы: `CLIENT_MASTER_CHAT_ID`, `CLIENT_CHAT_ID`)

## Как формируется webhook URL
- Формула: `PUBLIC_BASE_URL + /webhook/<BOT_PATH_SECRET>`.
- В логах URL маскируется (секрет не печатается).

## Как проверять после деплоя
1. В логах старта есть `mode=webhook`.
2. Есть `deleteWebhook ok` и `setWebhook ok`.
3. `/health` отвечает `200`.
4. `POST /webhook/<BOT_PATH_SECRET>` отвечает `200`.
5. `/WEBAPP`, `/assets/webapp.bundle.js`, `/assets/webapp.bundle.css` отвечают `200`.
6. `python -m unittest discover -s tests -p 'test_*.py'` проходит локально.
