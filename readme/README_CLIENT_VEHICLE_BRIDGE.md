# Client/Vehicle Bridge Reference Dataset

## 1) Что это за база
`Client/Vehicle Bridge` — это временный **reference dataset** с нормализованными клиентами и автомобилями для поиска, enrichment и будущих интеграций.

Это **не runtime DB** проекта и **не замена** `DB_SQLITE_PATH`.

## 2) Происхождение
Датасет собран из ручной выгрузки и предварительной нормализации 1С-данных (клиенты, авто, история владения/обслуживания, проблемные телефоны, метрики).

## 3) Где лежат файлы
- `data/reference/client_vehicle_bridge/lira_normalized_database.xlsx`
- `data/reference/client_vehicle_bridge/lira_normalized_database.sqlite`
- `data/reference/client_vehicle_bridge/schema.md`

## 4) XLSX vs SQLite
- **XLSX**: удобен для ручной проверки, содержит комментарии/описания и листы (`Summary`, `Schema`, `SourceMap`).
- **SQLite**: удобен для SQL-проверок, repeatable joins, автоматических валидаций структуры.

## 5) Сущности
Текущий снимок включает:
- `clients`
- `vehicles`
- `vehicle_owner_history`
- `invalid_phones`
- `schema_dictionary`
- `summary_metrics`
- `SourceMap` (XLSX)

## 6) Ключевые поля для matching/enrichment
### Клиенты
- `client_external_id` (`client_code`)
- `full_name` (`client_name`)
- `normalized_phone` (`phone_norm`)
- `raw_phone` (`phone_raw`)
- `source_system`
- `source_record_id`

### Автомобили
- `vehicle_external_id` (`vehicle_code`)
- `owner_external_id` (`owner_client_code`)
- `owner_name`
- `normalized_vin` (`vin_norm`)
- `plate_number` (`plate_norm`)
- `brand_model` (`vehicle_model`)
- `latest_mileage`, `max_mileage`, `last_mileage_date`

## 7) Как использовать в проекте
- Для offline клиентского lookup (по телефону/ФИО/VIN).
- Для enrichment карточек заявок (owner hints, mileage context).
- Для quality-check и подготовки правил future dedup/matching.

Важное ограничение: runtime сервисы не должны автоматически подхватывать этот dataset без отдельной задачи/feature.

### Текущий runtime use-case (WebApp exact lookup)
- В runtime используется **только read-only lookup** для web/site заявок.
- Источник: `data/reference/client_vehicle_bridge/lira_normalized_database.sqlite` (предпочтительно к XLSX для программного поиска).
- Текущий ключ: только `phone_norm + client_name/client_name_norm` (exact deterministic match).
- При одном совпадении заявка получает `existing_client=true`; при `0` совпадений — `false`; при `>1` — conflict (`needs_review=true`).
- Lookup не меняет runtime production DB и не делает auto-merge с клиентской production-историей.

## 8) Future 1С bridge
Датасет является промежуточным контрактом между 1С-выгрузками и бот-контуром:
- фиксирует стабильные сущности и поля;
- задаёт нормализацию телефона/VIN;
- позволяет ввести контролируемый import/update pipeline.

## 9) Future import/update
Рекомендуемый цикл:
1. Загружать новый экспорт в staging.
2. Нормализовать телефоны/имена/VIN по правилам в `schema.md`.
3. Обновлять `client_external_id` и `vehicle_external_id` через upsert.
4. Отдельно вести `invalid_phones` и summary-метрики.
5. Отмечать источник (`source_system`) и дату batch.

## 10) Почему это reference dataset, а не runtime DB
- Runtime хранит операционные заявки, события, задачи и bot-состояние.
- Bridge dataset хранит внешний справочный слой клиентов/авто.
- У этих слоёв разные SLA, обновляемость и риск-профиль.

## 11) Обязательные правила нормализации
1. Телефон: только 10 цифр, без `+7`, ведущей `8`, скобок, пробелов, кавычек, дефисов.
2. Email не является основным ключом matching.
3. Порядок сопоставления клиента: `phone -> fio -> vin`.
4. VIN формата `no_vin_*` считается placeholder.
5. Пробег (`latest_mileage`, `max_mileage`, `last_mileage_date`) — отдельный полезный признак.
