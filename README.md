# Telegram Reviews Bot — Автоцентр Лира

Бот для сбора и анализа отзывов об автосервисе **Автоцентр Лира** (Нижний Новгород). В интерфейсе используется иконка 🛠️🚗.  
Адрес: Нижний Новгород, ул. Удмуртская, д. 10.  
Телефоны: +7 (831) 214-00-50, +7 (967) 711-50-50.  
Режим работы: Пн–Пт 09:00–19:00; Сб–Вс выходной.

## Railway + GitHub деплой
Если Railway привязан к GitHub, пуш в `main` автоматически запускает деплой.

**Обязательные переменные окружения:**
- `TELEGRAM_BOT_TOKEN`
- `DATABASE_URL` **или** набор `PG*`:
  - `PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD`, `PGDATABASE`
- AI ключи/настройки (`DEEPSEEK_API_KEY` или альтернативы)

**Опциональные переменные:**
- `WEBHOOK_URL` **или** `DOMAIN` (см. ниже)
- `SUPERADMIN_ID` (если нет — берётся первый ID из `REPORT_CHAT_IDS`)
- `OWNER_CHAT_ID` (если нужно явно задать chat_id владельца)
- `DIAG_TOKEN`
- `CRON_TOKEN`
- `CX_PROMPT_MODE` (`full|lite`)
- `AI_ENGINE`
- `REPORT_CHAT_IDS` (список админов, разделитель произвольный)

**Ключевые переменные для запуска/доступов (кратко):**
- `SUPERADMIN_ID` — гарантированный доступ владельца.
- `REPORT_CHAT_IDS` — список админов (seed и уведомления).
- `DATABASE_URL` — подключение к Postgres.
- `WEBHOOK_URL` — внешний адрес для webhook (или `DOMAIN`).

**Важно:** управление доступами теперь живёт в БД и управляется через бот — редактировать `REPORT_CHAT_IDS`/Railway UI не нужно (кроме первоначальной настройки владельца и БД).

## Webhook URL
Webhook формируется так:
1) если задан `WEBHOOK_URL`, используется он;
2) иначе берётся `DOMAIN` и формируется `https://{DOMAIN}/webhook/{BOT_PATH_SECRET}`.

Если не задано ни `WEBHOOK_URL`, ни `DOMAIN`, установка webhook будет пропущена и это отразится в `/diag`.

## Управление доступами
Роли:
- `owner` — владелец (SUPERADMIN_ID)
- `staff` — сотрудники (полный доступ + админ-уведомления)
- `user` — доступ без админ-уведомлений

Команды владельца:
- `/invite <id> [role=staff|user] [note=...]`
- `/kick <id>`

Также доступен UI: `⚙️ Настройки → 👥 Управление доступами`.

## Добавление отзывов
`➕ Добавить отзыв` → выбор метода:
1) ✍️ **Ручной ввод**  
2) 🔗 **По ссылке** — бот пробует извлечь данные из публичной ссылки. Если парсинг заблокирован/неполный, бот задаст уточняющие вопросы (площадка/рейтинг/автор/текст).  

Перед сохранением бот показывает сводку и спрашивает подтверждение.

## Диагностика
`/diag` показывает статус БД, webhook, роли и схему таблиц.  
`/diag json` — JSON-версия для удобной отладки.  
`/diag/ai` — проверка AI, возврат `engine`, `model`, `http_status`, `raw_preview`.

## Self-test
Локально:
```bash
python scripts/selftest.py
```

## Миграции (idempotent SQL)
**A) access_users table upgrade**
```sql
CREATE TABLE IF NOT EXISTS access_users (
  user_id BIGINT PRIMARY KEY,
  role TEXT NOT NULL DEFAULT 'user',
  added_by BIGINT,
  note TEXT,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  added_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE access_users ADD COLUMN IF NOT EXISTS user_id BIGINT;
ALTER TABLE access_users ADD COLUMN IF NOT EXISTS role TEXT DEFAULT 'user';
ALTER TABLE access_users ADD COLUMN IF NOT EXISTS added_by BIGINT;
ALTER TABLE access_users ADD COLUMN IF NOT EXISTS note TEXT;
ALTER TABLE access_users ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;
ALTER TABLE access_users ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT now();
ALTER TABLE access_users ADD COLUMN IF NOT EXISTS added_at TIMESTAMPTZ DEFAULT now();

INSERT INTO access_users (user_id, role, added_by, is_active)
VALUES (:OWNER_ID, 'owner', :OWNER_ID, TRUE)
ON CONFLICT (user_id)
DO UPDATE SET role='owner', is_active=TRUE;
```

**B) reviews compatibility**
```sql
ALTER TABLE reviews ADD COLUMN IF NOT EXISTS text TEXT;
ALTER TABLE reviews ADD COLUMN IF NOT EXISTS review_text TEXT;
ALTER TABLE reviews ADD COLUMN IF NOT EXISTS meta JSONB NOT NULL DEFAULT '{}'::jsonb;

UPDATE reviews SET review_text = text WHERE review_text IS NULL AND text IS NOT NULL;
UPDATE reviews SET text = review_text WHERE text IS NULL AND review_text IS NOT NULL;
UPDATE reviews SET text = '' WHERE text IS NULL;
ALTER TABLE reviews ALTER COLUMN text SET NOT NULL;
```
