# README_AFTER_DEPLOY

## 1) Overview
Проект разделён на два независимых процесса:
- `client_bot_service` — клиентский бот, WebApp, заявки, мастера, статусы, закреп.
- `reviews_bot_service` — бот отзывов, публикации, AI-анализ, архитектурные заготовки для Email/1С/VK/Max.

Текущий функционал **сохранён** через совместимость с существующими runtime-модулями (`bots/client_bot/main.py` и `main.py`) с постепенным выносом в новую структуру.

## 2) Архитектура

```text
/services
  /client_bot_service
    /app
      main.py
      config.py
      /models
      /storage
      /telegram
      /webapp
      /integrations
      /utils
  /reviews_bot_service
    /app
      main.py
      config.py
      /reviews
      /integrations
/data
  clients.jsonl
  tickets.jsonl
  system.json
```

### Runtime принципы
- Единый `unified main.py` не используется как оркестратор для обоих доменов.
- Каждый сервис запускается отдельно (`python -m app.main` из директории сервиса).
- По умолчанию режим polling; webhook остаётся опциональным в legacy-логике.
- Сервисы не вызывают друг друга напрямую.

## 3) ENV таблицы

### client_bot_service
- `CLIENT_TELEGRAM_BOT_TOKEN` (fallback: `TELEGRAM_BOT_TOKEN`)
- `CLIENT_BOT_MODE` (`polling` по умолчанию)
- `CLIENT_SERVICE_HOST` (`0.0.0.0`)
- `CLIENT_SERVICE_PORT` (`8010`)
- `CLIENT_DATA_DIR` (`data`)

### reviews_bot_service
- `TELEGRAM_BOT_TOKEN`
- `REVIEWS_SERVICE_HOST` (`0.0.0.0`)
- `REVIEWS_SERVICE_PORT` (`8020`)

### совместимость
Существующие переменные legacy-модулей продолжают работать (AI engine, webhook/domain, routing/admin/master и т.д.).

## 4) WebApp маршруты
Основные маршруты client_bot runtime:
- `GET /WEBAPP` и `GET /WEBAPP/`
- `GET /WEBAPP/config.json`
- `GET /WEBAPP/<static>`
- `GET /api/webapp/health`
- `GET /api/webapp/lookup`
- `POST /api/webapp/session`
- `POST /api/webapp/submit`

Гарантии:
- обязательный `phone`;
- серверная нормализация телефона к `+7XXXXXXXXXX`;
- валидация `initData`;
- поддержка theme в фронтенде (унаследована из legacy webapp).

## 5) Ticket flow
- intake: Telegram private messages/WebApp submit;
- создание тикета со статусом `new`;
- маршрутизация мастерам (уведомления в мастер-канал/чат/личку по текущей конфигурации);
- переходы статусов: `new`, `in_progress`, `waiting_data`, `processed`, `archived`;
- `postponed` заложен в модели, поле `postponed_until` присутствует для планировщика.

## 6) Master flow
- Роли: admin/master.
- Источники мастеров: ENV + админ-действия в runtime.
- Для мастер-чата включён фильтр:
  - текст в супергруппе без команды не создаёт заявку;
  - реакции только на команды/inline callback.
- Ответ клиенту: через карточку заявки и callback-диалоги legacy runtime.

## 7) Pin flow
- используется механизм pinned-message legacy runtime;
- хранится `pinned_message_id` в runtime storage;
- попытка `edit` при наличии pinned;
- fallback на создание нового закрепа при невозможности edit;
- защита от размножения закрепов.

## 8) Storage
Гибридная стратегия:
- основной слой: текстовые файлы в `/data` (`clients.jsonl`, `tickets.jsonl`, `system.json`);
- адаптер `github_storage.py` и режим с `GITHUB_TOKEN` подготовлены для синхронизации коммитами;
- при отсутствии токена — локальный режим.

### Клиентская картотека
Модель `Client` хранит:
- `telegram_user_id`, `telegram_username`, `full_name`
- `phones[]`, `car_numbers[]`, `vin_codes[]`
- `vk_username`, `max_username`, `email`
- `created_at`, `updated_at`, `source_tags[]`

Логика обновления: только расширение массивов без разрушения существующих данных.

## 9) Будущие интеграции
Созданы заглушки:
- `future_1c_adapter.py`
- `future_vk_adapter.py`
- `future_max_adapter.py`
- `future_email_adapter.py` (в reviews service)

Единый интерфейс:
```python
class ExternalSourceAdapter:
    def import_contacts(self): ...
    def import_requests(self): ...
    def sync_client(self, client): ...
```

## 10) Ограничения Telegram
- длина сообщений, rate limit, ограничения edit/pin;
- в группах/супергруппах бот зависит от privacy-mode и контекста команд;
- `initData` Telegram WebApp ограничен по времени жизни подписи.

## 11) Команды запуска

### Client bot service
```bash
cd services/client_bot_service
python -m app.main
```

### Reviews bot service
```bash
cd services/reviews_bot_service
python -m app.main
```

### Тесты
```bash
python -m unittest discover -s tests -p 'test_*.py'
```

### CI
Workflow: `.github/workflows/tests.yml`.
