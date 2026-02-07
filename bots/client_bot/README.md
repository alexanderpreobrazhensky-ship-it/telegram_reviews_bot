# client_bot

`client_bot` — клиентский Telegram-бот автосервиса «Автоцентр Лира». Общается по-русски, вежливо и без лишних эмодзи, помогает оформить обращение и передать его мастерам. Бот работает **только через polling** и при старте делает `deleteWebhook`, чтобы исключить конфликты с webhook.

## Возможности

- Диалоги по сценариям: запись, ремонт, запчасти, прошлый визит, другое.
- Передача заявок мастерам, статусы, напоминания, обработка медиа (клиенту вложения запрещены, мастерам передаются).
- AI (DeepSeek) с автоfallback и safeguard: без цен, сроков, наличия, выдумок.
- Админ-меню: самодиагностика, заявки, выгрузка, статистика, логи, админы, настройки.

## Один Railway service, два бота

`client_bot` и `reviews_bot` могут работать в одном Railway service. Для разделения конфигурации используются переменные окружения с префиксом `CLIENT_`. Это позволяет держать **два токена** и разные настройки в одном сервисе без конфликтов.

- `client_bot` читает **только** `CLIENT_TELEGRAM_BOT_TOKEN` (или `TELEGRAM_BOT_TOKEN_CLIENT` как fallback).
- `client_bot` всегда работает через polling и сам удаляет webhook.
- `reviews_bot` может использовать webhook независимо.

## Переменные окружения

### Токен и таймзона

- `CLIENT_TELEGRAM_BOT_TOKEN` — токен BotFather для клиентского бота (основной).
- `TELEGRAM_BOT_TOKEN_CLIENT` — fallback токена, если основной не задан.
- `TIMEZONE` — часовой пояс, по умолчанию `Europe/Moscow`.

### Мастера

- `MASTER_USERNAMES` — список Telegram-юзернеймов мастеров через запятую (обязательно, используется в UI).
- `CLIENT_MASTER_CHAT_IDS` — опционально, список chat_id мастеров (для диагностики количества).
- `MASTER_CHAT_IDS` — в `client_bot` не используется; не требуется.

### AI (DeepSeek)

- `CLIENT_DEEPSEEK_API_KEY` (fallback: `DEEPSEEK_API_KEY`).
- `CLIENT_DEEPSEEK_BASE_URL` (fallback: `DEEPSEEK_BASE_URL`).
- `CLIENT_DEEPSEEK_MODEL` (fallback: `DEEPSEEK_MODEL`).
- `CLIENT_AI_TIMEOUT_SECONDS` (fallback: `AI_TIMEOUT_SECONDS`, по умолчанию `10`).
- `CLIENT_FORCE_FALLBACK` (fallback: `FORCE_FALLBACK`, `1` — всегда fallback).

### Админ

- `CLIENT_ADMIN_IDS` — список tg_id администраторов через запятую.

### Напоминания

- `CLIENT_REMINDER_MINUTES` (fallback: `REMINDER_MINUTES`, по умолчанию `30`).
  Для теста можно поставить `CLIENT_REMINDER_MINUTES=1`.

### Storage и логи

- Storage: `bots/client_bot/storage.json`.
- Логи: `bots/client_bot/logs/client_bot.log` (префиксы `[client_bot]`, `[ai]`, `[polling]`, `[admin]`, `[storage]`).

### WebApp (Mini App)

- `WEBAPP_URL` — публичный URL на `/webapp`, используется для кнопки «✨ Открыть меню (WebApp)`.
- `LIRA_PHONE` — телефон для кнопки «Позвонить» (опционально).
- `LIRA_ADDRESS` — адрес, по умолчанию `Удмуртская 10`.
- `LIRA_MAP_URL` — ссылка на карту (опционально; если не задана, строится по адресу).
- `CLIENT_WEBAPP_PORT` — порт для локальной раздачи WebApp (опционально, если `PORT` не задан).

## Локальный запуск

```bash
cd /workspace/telegram_reviews_bot/bots/client_bot
python main.py
```

Перед запуском задайте переменные окружения (минимум `CLIENT_TELEGRAM_BOT_TOKEN`, `MASTER_USERNAMES`, `CLIENT_ADMIN_IDS`).

## Railway деплой (общий порядок)

1. В одном Railway service задайте **только `CLIENT_*` переменные** для `client_bot`.
2. Убедитесь, что `CLIENT_TELEGRAM_BOT_TOKEN` — отдельный токен клиентского бота.
3. Выполните redeploy сервиса.
4. В логах проверьте строки:
   - `client_bot token source: ...`
   - `deleteWebhook ok` или предупреждение, что webhook уже удалён.

## Типовые проблемы и решения

- **409 Conflict (webhook vs polling)**
  `client_bot` сам вызывает `deleteWebhook` при старте и при 409. Проверьте логи `[polling]`.

- **Мастер не получает сообщения**
  Мастер должен **написать боту первым**. Убедитесь в корректности `MASTER_USERNAMES` или `CLIENT_MASTER_CHAT_IDS`.

- **400 Bad Request (reply_markup)**
  Обычно связано с некорректной клавиатурой. Ищите подробности в `client_bot.log` по префиксу `[client_bot]`.

- **AI упал → автоfallback**
  Если DeepSeek недоступен, бот автоматически переключится на fallback. Проверка: установите `CLIENT_FORCE_FALLBACK=1`.

## Безопасность

- Не храните токены и ключи в репозитории.
- Не логируйте секреты (токены/ключи) вручную.
