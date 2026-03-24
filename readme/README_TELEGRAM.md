# Telegram

## Active webhook routes
- `POST /telegram/client_bot/webhook`
- `POST /telegram/master_bot/webhook`
- `POST /telegram/integration_bot/webhook`

## Master bot
- Inline callback main menu.
- Поддерживаются: новые заявки, в работе, архив, поиск, quality cases, инструкция, диагностика, логи, доступы, AI (admin).
- Карточка заявки: взять в работу, запросить данные, обработана(+substatus), в сервисе, завершить, комментарий, подробнее.
- Legacy callbacks маппятся в актуальные действия и не ломают UX.

## Navigation
- `⬅️ Назад` возвращает на предыдущий экран (включая AI submenu/input states).
- `🏠 В меню` возвращает в корневое меню.

## Integration bot
Telegram-only operator bot.
Поддерживает button-first режим + slash command fallback.

## Clarification routing
Для заявок из Telegram первичный outbound канал — Telegram;
fallback в MAX допускается только при подтверждённом `maxId`.
