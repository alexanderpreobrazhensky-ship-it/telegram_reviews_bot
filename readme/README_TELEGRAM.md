# Telegram

## Active routes
- `/telegram/client_bot/webhook`
- `/telegram/master_bot/webhook`
- `/telegram/integration_bot/webhook`

## Master bot
- Uses inline callback main menu.
- Valid menu callbacks do not fall through to `/help` fallback.
- Legacy request-card callbacks are compatibility-mapped and refresh the card UX.

## Client clarification routing
- Telegram-source requests send outbound clarification back to Telegram first.
- Fallback to MAX is allowed only if a real `maxId` exists.

## Integration bot
- Remains Telegram-only by design.
- Webhook route: `POST /telegram/integration_bot/webhook`.
- Primary UX is button-first: reply keyboard sections `Все события`, `Ошибки`, `В ожидании`, `Статистика`, `Инструкция`, `Самодиагностика`.
- Slash commands remain supported as fallback: `/start`, `/help`, `/selfcheck` (`/diag`), `/events`, `/failed`, `/pending`, `/stats`, `/event <id>`, `/retry <id>`, `/ignore <id>`.
- Event cards expose inline actions `Подробнее`, `Повторить`, `Игнорировать`.
- `/help` and the `Инструкция` button return the same operator-facing usage guide in Russian.
- `/selfcheck` and `Самодиагностика` run real checks for token presence, SQLite/file DB access, integration event store readability, route/dependency availability, scheduler persistence access, event counters, and obvious config issues.
- Empty stores are handled explicitly: bot returns human-readable empty states instead of silent failures.
