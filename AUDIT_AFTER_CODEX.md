# AUDIT_AFTER_CODEX

## 1) Что исправлено по BotHost проблемам

### 1.1 Нестабильный entrypoint / попытки запускать Node webapp
**Проблема:** BotHost мог выбирать не тот стартовый путь (в т.ч. Node/webapp сценарий).

**Исправление:**
- корневой `main.py` оставлен исключительно как Python entrypoint client-service;
- launcher-конфиги приведены к единой команде `python main.py`:
  - `Procfile`
  - `railway.toml`
  - `run_all.sh`

**Результат:** старт только client-bot service, без запуска `webapp/app.js` как процесса.

---

### 1.2 `client_bot token missing`
**Проблема:** риск тихого skip при отсутствии одного конкретного env.

**Исправление:** единый chain резолва токена:
1) `CLIENT_TELEGRAM_BOT_TOKEN`
2) `TELEGRAM_BOT_TOKEN`
3) `BOT_API_TOKEN`
4) `API_TOKEN`

При отсутствии всех — `RuntimeError`.
В логи выводится только `token_source`.

---

### 1.3 Путаница PORT/HOST/DOMAIN и double-scheme URL
**Исправление:**
- порт: `PORT -> CLIENT_SERVICE_PORT -> 8000`;
- host: `CLIENT_SERVICE_HOST` (default `0.0.0.0`);
- webapp URL: `CLIENT_WEBAPP_URL -> WEBAPP_URL -> https://{DOMAIN}{WEBAPP_PATH}`;
- normalize URL (удаление `https://https://`, `https://http://`, trim, https-only);
- невалидные URL отбрасываются, логируется warning.

---

### 1.4 WebApp session/submit стабильность
**Подтверждено в коде и тестах:**
- `/WEBAPP`, `/app.css`, `/app.js`, `/WEBAPP/config.json` доступны;
- `/api/webapp/session` выдаёт `session_token`;
- `/api/webapp/submit` поддерживает `session_token` и fallback `initData`;
- ошибки: `phone_required`, `invalid_init_data`, `session_expired`.

---

### 1.5 Intake private chat и картотека
**Сделано:**
- `clients.jsonl` в корне остаётся default registry;
- на private message создаётся/обновляется тикет;
- если нет телефона — `waiting_data` + запрос телефона;
- в тикет добавлены поля `original_message_text` и `source=telegram_chat`.

---

### 1.6 Доставка мастерам (DM + чат)
**Уточнена логика маршрутизации:**
- нет `CLIENT_MASTERS_CHAT_ID` → DM only;
- нет `CLIENT_MASTER_USER_IDS` → chat only;
- если оба есть → `CLIENT_NOTIFY_MODE`.

Ошибки DM не прерывают остальную рассылку.

---

### 1.7 Master chat filter
**Подтверждено:** обычный текст в master chat без команды не создаёт тикет.
Добавлен отдельный тест.

---

### 1.8 Pin flow
**Статус:** логика уже соответствовала требованиям:
- `pinned_message_id` как int;
- `message is not modified` считается успешным апдейтом;
- fallback при `message to edit not found` / rights error.

---

## 2) Изменённые файлы

1. `main.py`
2. `Procfile`
3. `railway.toml`
4. `run_all.sh`
5. `bots/client_bot/main.py`
6. `tests/test_bothost_contract.py`
7. `tests/test_master_chat_filter.py`
8. `README_AFTER_DEPLOY.md`
9. `AUDIT_AFTER_CODEX.md`

---

## 3) Какие пункты BotHost-логов закрыты

- ✅ Нет обязательной зависимости от Node entrypoint.
- ✅ Старт через python-only entrypoint.
- ✅ Нет `token missing` при наличии любого из 4 token env.
- ✅ Нет тихого skip при отсутствии токена — явный `RuntimeError`.
- ✅ Нормализуется WebApp URL, убираются double-scheme кейсы.
- ✅ В master-chat plain text не рождает тикеты.
- ✅ Маршрутизация DM/chat соответствует прод-правилам.

---

## 4) Чеклист ручной проверки после деплоя

### A. Startup
- [ ] В логах есть `client_bot_service startup ... token_source=...`.
- [ ] Нет stacktrace вида `window is not defined`.
- [ ] Нет попыток запускать `/app/bots/client_bot/webapp/app.js` как entrypoint.

### B. Token/env
- [ ] При установленном `CLIENT_TELEGRAM_BOT_TOKEN` бот стартует.
- [ ] При пустом `CLIENT_TELEGRAM_BOT_TOKEN`, но установленном `TELEGRAM_BOT_TOKEN` — стартует.
- [ ] При полном отсутствии token env — процесс падает с `RuntimeError`.

### C. WebApp URL/menu
- [ ] `setChatMenuButton` проходит без ошибок `invalid URL`.
- [ ] URL в меню корректный и https-only.

### D. WebApp API
- [ ] `GET /WEBAPP` → 200
- [ ] `GET /app.css` → 200
- [ ] `GET /app.js` → 200
- [ ] `GET /WEBAPP/config.json` → 200
- [ ] `POST /api/webapp/session` с валидным initData → 200 + session token
- [ ] `POST /api/webapp/submit` без телефона → 400 `phone_required`
- [ ] `POST /api/webapp/submit` с телефоном и валидной сессией/initData → 200

### E. Tickets
- [ ] Любой private text клиента создаёт тикет.
- [ ] Клиент попадает в `clients.jsonl`.
- [ ] Без телефона тикет виден мастерам как `waiting_data`.
- [ ] С телефоном тикет идёт как `new`.

### F. Master delivery and chat filter
- [ ] Если задан только master chat — тикет доходит в чат.
- [ ] Если заданы только master user ids — тикет доходит в DM.
- [ ] Если заданы и чат, и DM — применяется `CLIENT_NOTIFY_MODE`.
- [ ] Plain text в master chat (без команды) не создаёт новый тикет.

### G. Pin
- [ ] Повторный деплой не создаёт дубликаты pin при неизменном тексте.
- [ ] При удалённом старом pin бот делает fallback и сохраняет новый `pinned_message_id`.

---

## 5) Прогон тестов (локально)

Основной прогон:
```bash
python -m unittest discover -s tests -p 'test_*.py'
```

Покрыто:
- BotHost contract (entrypoint, port priority, token chain, URL normalize).
- WebApp static/session/submit.
- Master chat filter.

---

## 6) Known limitations

1. В репозитории всё ещё присутствуют Railway-исторические файлы/документация как артефакты, но runtime-старт для production унифицирован на `python main.py`.
2. Polling остаётся целевым режимом BotHost; webhook сценарий не основной.
3. Если мастер не нажал `/start` в ЛС, DM может вернуть `403` (это штатно; используйте master-chat и/или попросите мастера активировать бота).
4. В тестах есть `ResourceWarning` в одном legacy-тесте на static routes (не влияет на pass/fail, но можно отдельно почистить закрытием file handles во всех тестах).
