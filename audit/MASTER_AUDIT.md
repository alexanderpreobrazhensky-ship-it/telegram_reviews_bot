# MASTER_AUDIT

`audit/MASTER_AUDIT.md` — **единственный** актуальный audit source of truth по репозиторию.

Дата аудита: **2026-03-25 (UTC)**.
Фокус: code audit + repository audit + architecture/flow/config/doc consistency audit (не только smoke/runtime).

---

## 1. Executive Summary

### Ключевые выводы
- **Node runtime-контур подтверждён**: `app.js` -> `src/server/index.js` + инфраструктурные модули (`db`, scheduler, email poller, ai infra). **[confirmed]**
- **WebApp request flow в коде цельный**: валидация -> create -> SQLite persist (`status=new`) -> уведомления Telegram/MAX -> диагностический trace `webapp_request_flow:last`. **[confirmed]**
- **Reference dataset lookup (existing client)** реализован как отдельный read-only SQLite слой с phone-primary exact matching и явной диагностикой недоступности. **[confirmed]**
- **AI diagnostics и runtime override архитектурно разделены** (config validation / primary / fallback / final diagnostics status), но “production-ready” зависит от валидной env-конфигурации и провайдеров. **[partially confirmed]**
- **Telegram/MAX parity** на уровне source-of-truth данных есть (единый DB/статусная модель), но фактическая parity уведомлений и UX зависит от MAX env и наличия получателей. **[partially confirmed]**
- **Email intake/T-Business контур реализован**, включая IMAP polling, дедупликацию, PDF parsing, detection scoring, priority=high, но требуется runtime-подтверждение с реальным ящиком/папкой и боевыми письмами. **[partially confirmed]**
- **Manager reports**: кнопочный admin-only flow в master bot + `/api/reports/*` + snapshots/export реализованы. **[confirmed]**

### Общий статус известных проблем (fixed / partially fixed / not fixed)
1) AI / diagnostics / override: **partially fixed**
2) Reference dataset / existing lookup: **fixed (code-level)**
3) WebApp request list visibility: **fixed (code-level)**
4) Telegram/MAX parity: **partially fixed**
5) `wasClientBefore`/VIN rule: **fixed (frontend+backend)**
6) Email intake / T-Business: **partially fixed**
7) Status/archive/substatus integrity: **fixed (code-level)**
8) Master bot button-only UX: **partially fixed** (есть текстовые команды как fallback)
9) Reports for manager admin-only: **fixed**

---

## 2. Repository Shape / Active Runtime Contour

### Active production contour (проверено)
- Entry/runtime: `app.js`, `src/server/index.js`, `src/infrastructure/config/index.js`, `src/infrastructure/db/index.js`.
- Core/domain/application: `src/core/**`.
- Interfaces/channels: `src/interfaces/**` (client/master/integration bots + shared adapters/security).
- Integrations: `src/integrations/**` (email, one_c skeleton).
- Web: `public/index.html`, `public/webapp.js`, `public/styles.css`.
- Deploy/runtime artifacts: `Dockerfile`, `.bothost/entrypoint.conf`, `package.json`.
- Docs: `readme/**`.
- Audit target: `audit/MASTER_AUDIT.md`.

Статус: **[confirmed]**.

### Support / legacy / potentially misleading
- `legacy/index.js` — shim-переход на `app.js` (явно deprecated). **[confirmed]**
- `bots/client_bot/*.py`, `services/*.py`, `shared/*.py` — отдельный Python-контур, не являющийся активным Node production path текущего runtime. Может вводить в заблуждение при чтении repo. **[confirmed]**
- `review.html` присутствует вне `public/` и не участвует в active route map Node-сервера. **[confirmed]**

Риск: смешение Node и legacy Python логики при онбординге/поддержке. **[confirmed]**

---

## 3. Runtime Architecture

### Startup chain
`bootstrap()` (`app.js`) выполняет:
1. `loadConfig()`
2. DB runtime info + `initializeStore()`
3. `createServer()`
4. `initializeAiInfrastructure()`
5. integration runtime hooks (master notifier, ai service)
6. scheduler start
7. email intake poller start + initial run
8. MAX webhook subscription reconciliation

Статус: **[confirmed]**.

### HTTP route map (ключевое)
- Health: `/health`, `/health/db`, `/health/max`
- Internal/admin: `/internal/requests`, `/internal/export`, `/internal/diagnostics`, `/internal/logs`, `/internal/reports`
- Client requests API: `/api/client/requests/*`
- Integrations: `/api/integrations/*`
- Reports API: `/api/reports/*` (admin gated)
- Webhooks: регистрируются через `src/interfaces/*/index.js`

Статус: **[confirmed]**.

### Service wiring
- Репозитории: `createRepositories({ db })`
- Existing lookup service: `createReferenceClientLookup`
- AI infra: runtime settings + diagnostics + provider registry
- Reporting service: отдельный application service

Статус: **[confirmed]**.

---

## 4. Config / ENV

### Canonical env
- Централизованно загружается `loadConfig()`; есть required/optional/legacy карты и `envAudit` с `requiredMissing`, `deprecatedConfigured`, `legacyAiDetected/ignored/used`, `unknownConfigured`.
- Fail-fast только при `CONFIG_STRICT=true` (или production default через NODE_ENV), иначе missing required env не валит запуск.

Статус: **[confirmed]**.

### AI env contract
- Canonical: `AI_*` (provider/model/fallback/timeout/proxy/keys/allowedProviders/diagnostics).
- Legacy aliases поддерживаются и явно размечаются в resolution метаданных.

Статус: **[confirmed]**.

### Email intake env contract
- Полный контракт для IMAP, matching и T-Business priority задан в config.

Статус: **[confirmed]**.

### Reference dataset env/path contract
- Явные override переменные: `REFERENCE_CLIENT_LOOKUP_DATASET_PATH` / `REFERENCE_CLIENT_LOOKUP_SQLITE_PATH`.
- При отсутствии override — автопоиск через предопределённые candidate paths.

Статус: **[confirmed]**.

---

## 5. Persistence

### Runtime DB
- `better-sqlite3`, WAL, foreign_keys=ON, schema bootstrap + optional column migrations.
- Canonical tables включают requests, request_events, analytics_events, tasks, staff_users, quality_cases, report_snapshots и др.

Статус: **[confirmed]**.

### Status/event integrity
- При создании request пишутся request + created/status_changed/integration_sync_pending events + analytics `request_created`.
- `listRequests` сортирует `created_at DESC`.

Статус: **[confirmed]**.

### Legacy JSON path
- Есть migration/import path из legacy JSON (`DB_JSON_IMPORT_PATH` / fallback), но canonical runtime — SQLite.

Статус: **[confirmed]**.

### Separation production DB vs reference DB
- Runtime заявки живут в основной SQLite (`DB_SQLITE_PATH`).
- Reference client lookup использует отдельную read-only SQLite dataset.

Статус: **[confirmed]**.

---

## 6. Telegram / MAX / Bots

### Master bot
- Кнопочные меню: Новые, В работе, Архив, Поиск, Quality cases, Инструкция, Диагностика, Логи, Доступы, AI, Отчёты.
- Request-card кнопки статусных действий и комментариев.
- Ролевой контроль staff/admin.

Статус: **[confirmed]**.

### Telegram/MAX webhook posture
- MAX роуты проходят отдельную проверку `validateMaxWebhookRequest`: path/method/max enabled/token/secret/body.
- Аналитика по rejected/received webhooks фиксируется.

Статус: **[confirmed]**.

### MAX parity
- Единый request source-of-truth (SQLite + одинаковая статусная модель).
- Уведомление в MAX masters выполняется в `duplicateToMastersChat()` по списку `MAX_MASTER_BOT_ADMIN_IDS`.
- Если MAX env/админы не настроены — attempted=false, parity фактически деградирует.

Статус: **[partially confirmed]**.

---

## 7. WebApp

### Validation contract
- Frontend (`public/webapp.js`) и backend (`validateClientRequestPayload`) синхронизированы:
  - phone = 10 digits
  - `wasClientBefore` обязателен (`yes|no`)
  - VIN обязателен только при `wasClientBefore=no`

Статус: **[confirmed]**.

### Request creation flow
- Endpoint `/api/client/requests/*`:
  - rate-limit
  - validation
  - dedupe check
  - `createClientRequest()`
  - notify masters (Telegram + MAX)
  - list visibility check (`status=new` список)
  - сохранение `webapp_request_flow:last`

Статус: **[confirmed]**.

### Existing client integration
- В payload сохраняются `existing_client`, `needs_review`, `client_match_basis`, matched reference ids/source/snapshot.

Статус: **[confirmed]**.

---

## 8. Email Intake / T-Business

### Architecture
- `createEmailIntakePoller`: IMAP connect -> mailboxOpen -> fetch by UID delta -> parse -> integration event.
- `integrationService`: normalize/parse/match/create request + sync metadata + master notify.

Статус: **[confirmed]**.

### Idempotency
- dedupe key по `message-id` либо content hash (subject + time + body hash).
- повторные события не перерабатываются в новые заявки.

Статус: **[confirmed]**.

### T-Business path
- Detection scoring по sender/subject/body/pdf.
- При detection: `source_provider=t_business`, `priority=EMAIL_SOURCE_TBUSINESS_PRIORITY` (default high).

Статус: **[confirmed]**.

### Runtime readiness gap
- Без реального IMAP окружения нельзя подтвердить production-устойчивость polling/folder auth/операционные алерты.

Статус: **[not confirmed без runtime]**.

---

## 9. AI / AI Diagnostics / Runtime Override

### Architecture
- Provider registry + provider/model compatibility rules.
- Runtime settings (active provider/model/fallback, ai enabled flags) хранятся в meta.
- `resolveAiConfig()` отделяет configured vs effective + override presence/validity.

Статус: **[confirmed]**.

### Diagnostics separation
- `runHealthCheck` формирует отдельные стадии: config validation / primary provider / fallback provider / final diagnostics status.
- Ошибки конфигурации (`CONFIG_INVALID`) отделены от provider failures.

Статус: **[confirmed]**.

### Proxy/deepseek orientation
- defaults: provider=`proxy`, model=`deepseek-chat`, allowed providers по умолчанию proxy/deepseek.

Статус: **[confirmed]**.

### Production readiness conclusion
- Кодовая архитектура и тесты зрелые, но реальная работоспособность AI в production определяется env + внешними провайдерами/сетью.

Статус: **[partially confirmed]**.

---

## 10. Reference Dataset / Existing Client Lookup

### Placement and loader
- Dataset path по умолчанию: `data/reference/client_vehicle_bridge/lira_normalized_database.sqlite` с множественными candidate fallbacks.
- loader диагностирует: configured/exist/readable/type/loaderStatus/lastLookup*.

Статус: **[confirmed]**.

### Matching contract
- Primary: exact normalized phone (10 digits).
- Outcomes:
  - exact -> `existing_client=true`, `client_match_basis=phone`
  - none -> `no_match`
  - multiple -> `multiple_phone_matches`, `needs_review=true`
  - unavailable -> `reference_dataset_unavailable`

Статус: **[confirmed]**.

### Rendering in master/internal surfaces
- Карточки и уведомления показывают existing client fields.

Статус: **[confirmed]**.

---

## 11. Status Model / Archive / Workflow

### Status/substatus model
- statuses: `new`, `in_progress`, `processed`, `in_service`, `completed`, `error`
- substatuses: `recorded`, `consulted`, `spam`, `waiting_decision`, `rejected`
- archive via completed/spam/rejected or archived flag.

Статус: **[confirmed]**.

### Transition integrity
- Явный transition graph + блокировка invalid переходов + immutability archive/completed.
- Для `processed` обязателен substatus; для `rejected` обязателен comment.

Статус: **[confirmed]**.

### Follow-up flows
- `waiting_decision_followup` и `consulted_followup` tasks создаются и обрабатываются scheduler.

Статус: **[confirmed]**.

---

## 12. Reports for Manager

### Реализация
- `reportingService` покрывает summary/funnel/sources/rejections/warranty/stuck/existing_new/t_business.
- `master_bot` имеет кнопочный flow выбора типа/периода + export.
- `/api/reports/*` и `/internal/reports` admin-gated.

Статус: **[confirmed]**.

### Gaps
- `buildMasterMetrics` сейчас stub-like (`masters: {}`), глубина master-аналитики ограничена.

Статус: **[confirmed]**.

---

## 13. Security

### Confirmed
- Internal/admin endpoints защищены allowlist (`admin_id` query/header + whitelist).
- MAX webhook security checks (secret/token/method/path/body).
- Маскирование секретов в AI diagnostics.

Статус: **[confirmed]**.

### Risks
- Internal auth модель опирается на ID allowlist (не IAM/role token).
- `/api/integrations/*` endpoints не имеют сильной аутентификации уровня production gateway.
- Reference dataset физически находится в repo tree (операционный риск утечки при неверном деплое/доступах).

Статус: **[confirmed]**.

---

## 14. Documentation Consistency

### Проверка
- Доки разложены по `readme/*`; есть отдельные README по env/runtime/persistence/max/security/testing.
- `readme/README_ENV.md` отражает canonical+legacy AI env и email intake контракт.

Статус: **[confirmed]**.

### Найденные несостыковки
- README_ENV содержит фразу “bridge dataset не требует env”, но код поддерживает explicit env override для lookup path; это не критично, но формулировку лучше уточнить.

Статус: **[partially confirmed]**.

---

## 15. Test Coverage / Validation Surface

### Что прогнано
- `npm test` (96/96 pass), включая:
  - AI infra/diagnostics/runtime override
  - reference lookup deterministic behavior
  - webapp validation `wasClientBefore`/VIN
  - report routes/admin-only
  - webhook/runtime regressions
  - sqlite persistence/migration

Статус: **[confirmed]**.

### Gaps
- Нет end-to-end боевого прогона с реальными Telegram/MAX токенами и IMAP mailbox.
- Нет нагрузочных/soak тестов email intake и report export на больших объёмах.

Статус: **[confirmed]**.

---

## 16. Known Issues Re-check

### 4.1 AI / AI Diagnostics
- Runtime override logic и provider/model validation присутствуют. **[confirmed]**
- Separation status vs diagnostics присутствует. **[confirmed]**
- “Доведён до рабочего состояния” в проде без env/provider подтверждения — нельзя утверждать. **[partially confirmed]**

### 4.2 Reference dataset / existing client lookup
- Loader/path resolution + phone lookup + render fields подтверждены кодом и тестами. **[confirmed]**
- Симптом `reference_dataset_unavailable` остаётся только как инфраструктурный случай missing/unreadable dataset. **[confirmed]**

### 4.3 WebApp request flow / list visibility
- Request persist + стартовый `new` + visibility check в `new` list + diagnostic trace реализованы. **[confirmed]**
- Runtime race/ops инциденты без живой среды полностью не исключаются. **[not confirmed без runtime]**

### 4.4 Telegram / MAX parity
- Общий source-of-truth и flow есть. **[confirmed]**
- parity фактической доставки зависит от MAX env/admin ids/token/secret. **[partially confirmed]**

### 4.5 Поле “Был у нас ранее” / VIN
- Frontend mandatory + backend mandatory + conditional VIN requiredness реализованы и покрыты тестами. **[confirmed]**

### 4.6 Email intake / T-Business
- Архитектура, parsing, dedupe, priority path и master delivery hooks есть. **[confirmed]**
- readiness в бою (Яндекс IMAP folder Т-БАНК ЗАЯВКИ) требует runtime-проверки с реальными creds. **[not confirmed без runtime]**

### 4.7 Status / archive / substatuses
- Модель и transition constraints явно реализованы, follow-up flows есть. **[confirmed]**

### 4.8 Master bot UX / button-only control planes
- Кнопочные control planes развиты (menu/back, reports, diagnostics, ai). **[confirmed]**
- Но текстовые команды тоже поддерживаются (не strict button-only). **[partially confirmed]**

### 4.9 Reports for manager
- Admin-only доступ + кнопочный flow + нужные report types присутствуют. **[confirmed]**
- Gap: master metrics detail ограничен. **[partially confirmed]**

---

## 17. Known Active Problems Re-check

| Проблема | Статус | Классификация | Комментарий |
|---|---|---|---|
| AI_DEEPSEEK_NOT_CONFIGURED / model mismatch / CONFIG_INVALID | **partially fixed** | partially confirmed | диагностика и валидация есть; зависит от env/provider runtime |
| existing client=false + reference_dataset_unavailable | **fixed (code-level)** | confirmed | loader и phone-primary lookup стабилизированы |
| WebApp заявка не в “Новые”/“В работе” | **fixed (code-level)** | confirmed | сохранение `new`, сортировка DESC, visibility trace |
| Telegram уведомление есть, MAX нет | **partially fixed** | partially confirmed | единый flow есть, но MAX delivery env-dependent |
| wasClientBefore/VIN rule | **fixed** | confirmed | frontend+backend+tests |
| Email intake / T-Business readiness | **partially fixed** | partially confirmed | код готов, боевой IMAP runtime не подтверждён |
| Status/archive integrity | **fixed** | confirmed | transition/immutability/follow-up защищены |
| Master bot UX buttons | **partially fixed** | partially confirmed | кнопки есть, но остаётся mixed mode с текстовыми командами |
| Reports admin-only | **fixed** | confirmed | bot + api gating + report suites |

---

## 18. Risks

1. **Operational parity risk (MAX):** при неполной MAX конфигурации заявки попадут в DB/Telegram, но не в MAX delivery plane.
2. **AI perception risk:** пользователи могут трактовать diagnostics как business-ready AI, хотя `AI_BUSINESS_USAGE_ENABLED` может быть OFF.
3. **Integration security risk:** публичные integration endpoints требуют более жёсткого perimeter/auth в production.
4. **Dual-stack repo risk:** legacy Python контур может приводить к ошибкам сопровождения и неверным fix placement.
5. **Email runtime fragility:** IMAP/folder credentials и внешние сетевые условия могут ломать intake при корректном коде.

Все пункты: **[confirmed]** как риски (не как фактические инциденты).

---

## 19. Recommended Next Fixes

1. **MAX parity hardening:** добавить обязательный startup health-gate для MAX master delivery (token/secret/admin_ids) и алерт, если parity неполная.
2. **AI readiness contract:** разделить в UI/diagnostics “infra OK” vs “business usage ON” более явно.
3. **Email E2E runbook:** автоматизировать smoke для IMAP папки Т-БАНК ЗАЯВКИ (sandbox mailbox).
4. **Security hardening:** подписывать/аутентифицировать `/api/integrations/*` (HMAC/JWT/gateway allowlist).
5. **Repo clarity:** добавить в README_PROJECT_OVERVIEW явный баннер “legacy Python contour (non-production)” и границы поддержки.
6. **Reports depth:** реализовать реальный `buildMasterMetrics` вместо заглушки.

Статус рекомендаций: **[confirmed as recommendations]**.

---

## 20. Confidence / Evidence Notes

### Уровень уверенности
- **Высокий (code-level):** архитектура, маршруты, валидации, DB модель, diagnostics, report gating.
- **Средний (runtime):** MAX parity, IMAP intake readiness, live AI provider health.

### Что подтверждено тестами
- Node tests: 96/96 pass (включая AI/reference/webapp/reports/status/regression).

### Что не подтверждено без runtime
- Реальная доставка Telegram/MAX в production.
- Реальная обработка IMAP в целевой почте/папке.
- Реальная доступность AI провайдера/прокси под боевой нагрузкой.

---

## 21. Прямые ответы на обязательные вопросы

1) **Реально ли AI-контур доведён до рабочего состояния?**
- Архитектурно — да; как production факт — **частично** (env/provider dependent). **[partially confirmed]**

2) **Реально ли existing client lookup с reference dataset работает?**
- На code/test уровне — **да** (phone-exact + diagnostics). **[confirmed]**

3) **Реально ли WebApp-заявки попадают в рабочие списки?**
- По коду и тестам — **да** (`new`, list visibility trace). **[confirmed]**

4) **Есть ли parity между Telegram и MAX?**
- Data/source-of-truth parity — **да**; delivery parity — **частично** (config dependent). **[partially confirmed]**

5) **Реализовано ли правило “Был у нас ранее” / VIN requiredness?**
- **Да**, фронт+бэк+тесты. **[confirmed]**

6) **В каком состоянии email intake / T-Business?**
- Кодово реализован и связен, но боевой runtime readiness без внешней проверки не финализирован. **[partially confirmed]**

7) **В каком состоянии manager reports?**
- Функционал есть, admin-only кнопками/endpoint-ами; часть аналитики (masters deep metrics) ограничена. **[confirmed + gap]**

8) **Какие проблемы остаются открытыми прямо сейчас?**
- MAX operational parity при неполной env.
- Live AI provider readiness.
- Боевой IMAP readiness.
- Усиление security perimeter integration/internal endpoints.

---

## 22. Validation Commands Snapshot

- `npm test` -> passed (96/96)
- Выборочный code audit по контурам: `app.js`, `src/server/index.js`, `src/infrastructure/config/index.js`, `src/infrastructure/db/index.js`, `src/infrastructure/referenceClientLookup.js`, `src/infrastructure/ai/*`, `src/integrations/email/*`, `src/interfaces/master_bot/index.js`, `public/webapp.js`, `src/core/application/reportingService.js`, `readme/*`, `Dockerfile`, `.bothost/entrypoint.conf`.


---

## 23. Runtime Re-check After Code Audit (2026-03-25 UTC)

Основа: данный re-check выполнен **поверх текущего `MASTER_AUDIT`**, без перезаписи предыдущей истории.

### Runtime evidence scope
- Runtime sandbox run: локальный запуск `createServer()` с отдельной SQLite (`/tmp/runtime-recheck-*.sqlite`), live HTTP submit по всем 5 webapp endpoint-ам, status transition, `/internal/diagnostics` snapshot, `integrationService.receiveIntegrationEvent()` для T-Business payload, `createEmailIntakePoller.runOnce()` и `ai.runDiagnostics()`.
- Dataset probe: прямой SQLite query по `data/reference/client_vehicle_bridge/lira_normalized_database.sqlite`.
- Regression confidence: `npm test` (96/96).

### 23.1 Reference Dataset / Existing Client Lookup

**Вердикт:** **[confirmed]** (в runtime sandbox + dataset probe).

Проверено:
1. Dataset физически присутствует в runtime path `data/reference/client_vehicle_bridge/lira_normalized_database.sqlite`, readable, loader status=`ready`, datasetType=`sqlite`. **[confirmed]**
2. Lookup использует SQLite dataset напрямую (`cacheStatus=sqlite_direct_no_cache`), не XLSX runtime parser. **[confirmed]**
3. Состояние `reference_dataset_unavailable` в проверенном runtime не воспроизводится (dataset exists/readable). **[confirmed]**
4. Business rule `exact phone match => existing_client=true` фактически срабатывает. **[confirmed]**
5. Контрольный номер `9506275333`:
   - номер есть в dataset (`clients.phone_norm=9506275333`, `client_code=ЦБ005355`, `client_name=Лукьянова Мария Алексеевна`),
   - lookup возвращает `existingClient=true`, `clientMatchBasis=phone`, `lookupStatus=exact_match`,
   - созданная webapp заявка получает `payload.existing_client=true`, `payload.client_match_basis=phone`,
   - в diagnostics lookup остаётся `available=true`, `lastLookupStatus=exact_match`. **[confirmed]**

Root cause на случай деградации (гипотеза, не инцидент текущего re-check): missing/unreadable dataset path при deploy или неверный env override (`REFERENCE_CLIENT_LOOKUP_*`). **[hypothesis only]**

### 23.2 WebApp Request Visibility

**Вердикт:** **[confirmed]** (runtime sandbox).

Проверено:
1. Реальный submit -> create -> SQLite persist отрабатывает для всех типов:
   - `service_request`, `consultation_request`, `parts_request`, `warranty_request`, `data_change_request`.
2. Все 5 созданных заявок получили `status=new`.
3. `db.listRequests({statuses:['new']})` содержит созданные записи (`newCount=5`).
4. `webapp_request_flow:last` фиксирует `requestReceived=true`, `requestPersisted=true`, `requestVisibleInNewRequests=true`.
5. Перевод мастером в работу подтверждён через `/api/requests/{id}/status` -> `status=in_progress`; запись видна в in-work выборке.

Отдельно по бизнес-правилам формы:
- `Был у нас ранее` обязателен: submit без поля возвращает validation error. **[confirmed]**
- `Был у нас ранее = Нет` => VIN обязателен: submit без VIN блокируется. **[confirmed]**
- `Был у нас ранее = Да` => VIN не обязателен: валидный submit проходит. **[confirmed]**

Вывод: после deploy-подобного запуска WebApp-заявки попадают в рабочие списки при штатном runtime. **[confirmed]**

### 23.3 Telegram / MAX Parity

**Вердикт:** **[partially confirmed]**.

Что подтверждено:
1. Единая request сущность (single source of truth в SQLite) создаётся один раз и используется обоими каналами. **[confirmed]**
2. Telegram delivery в sandbox отмечен как attempted/delivered (`telegramNotification.delivered=true` в trace текущего прогона). **[confirmed]**
3. MAX ветка вызывается (attempted=true, recipients=2), но фактическая доставка `delivered=0`. **[confirmed]**

Точный root cause отсутствия MAX-доставки в re-check:
- delivery logic пытается отправить, но получает `MAX sendMessage exception: fetch failed` при текущем окружении (невалидный/недоступный токен/endpoint), т.е. проблема operational env/connectivity, а не отсутствие create/list source-of-truth. **[confirmed]**

Итог parity:
- parity на уровне source-of-truth: **есть**. **[confirmed]**
- parity на уровне фактического notification UX: **неполная**. **[partially confirmed]**

### 23.4 Email Intake / T-Business Runtime Readiness

**Вердикт:** **[partially confirmed]**.

Что подтверждено:
1. T-Business processing path действительно создаёт request через integration flow:
   - event processingStatus=`processed`,
   - у request: `sourceChannel=email`, `payload.source_provider=t_business`, `payload.priority=high`,
   - existing client match и match basis заполняются (в тестовом payload: `existing_client=true`, `match_basis=phone`). **[confirmed]**

Что не подтверждено как production-ready:
2. IMAP runtime в целевом окружении не подтверждён: `poller.runOnce()` дал `lastPollResult=failed`, `connectionStatus=failed`, `folderStatus=failed`, `lastError=ECONNREFUSED 127.0.0.1:2993` для проверочного контура. **[not confirmed]**
3. Реальный доступ к mailbox/folder `Т-БАНК ЗАЯВКИ` в боевом провайдере не верифицирован данным запуском. **[not confirmed]**

Интерпретация метрик `processed / duplicates / failed_parse`:
- `processed` — число событий, дошедших до `integration event processingStatus=processed`.
- `duplicates` — события, отфильтрованные dedupe/повторной обработкой.
- `failed_parse` — количество PDF attachment parse failures (накапливается из `failedAttachmentParses`), это индикатор деградации parsing path, а не успешной обработки.

Следствие для кейса вида `878/0/878`: это не «нормальная стабильная работа», а сигнал, что обработка событий могла идти, но PDF parsing path системно падал (требуется разбор формата вложений/парсера/контента). **[confirmed interpretation]**

### 23.5 AI Runtime Readiness

**Вердикт:** **[partially confirmed]** (architecturally ready, operationally not ready в проверенном runtime).

Проверено:
1. Effective config и runtime resolution отображаются корректно (provider/model/sources, override flags). **[confirmed]**
2. Config validation/diagnostics separation работает: diagnostics вернули `status=CONFIG_INVALID` при `CONFIG_PROXY_NOT_CONFIGURED`. **[confirmed]**
3. Primary provider readiness не подтверждена (`primaryTestAttempted=false`, `proxyConfigured=false`, auth secrets missing). **[not confirmed]**
4. Fallback readiness не подтверждена (`fallbackConfigured=false`). **[not confirmed]**
5. Business usage состояние отдельно видимо (`AI_BUSINESS_USAGE_ENABLED=false`) и не должно трактоваться как business-ready AI даже при включённом infra. **[confirmed]**

Отдельный вывод:
- Текущий AI-контур можно считать **architecturally ready**, но не **operationally ready** без валидных provider/proxy credentials и успешных live probes. **[partially confirmed]**

### 23.6 Updated Operational Verdict

#### Ответы на ключевые вопросы
1. Работает ли existing client lookup в реальном runtime? — **Да, confirmed** (dataset доступен, lookup exact работает). 
2. Достаточно ли exact phone match? — **Да, confirmed** (`existing_client=true`, basis=phone).
3. Попадают ли WebApp-заявки в «Новые заявки»? — **Да, confirmed** (persist/new/list visibility).
4. Есть ли реальный Telegram/MAX parity? — **Частично**: source-of-truth parity есть, delivery parity в MAX неполная.
5. Работает ли T-Business intake фактически? — **Частично**: create-path подтверждён, IMAP/folder production readiness не подтверждена.
6. Готов ли AI контур operationally? — **Нет, не подтверждено**; пока architecturally ready + diagnostics aware.
7. Что остаётся открытой проблемой прямо сейчас? — MAX delivery env/connectivity, IMAP mailbox/folder operational readiness, AI provider/proxy readiness.

#### Updated fixed status
- Reference dataset / existing client lookup: **fixed (runtime confirmed)**.
- WebApp -> DB -> list visibility: **fixed (runtime confirmed)**.
- Telegram/MAX parity: **partially fixed**.
- Email intake / T-Business: **partially fixed**.
- AI runtime readiness: **not fixed operationally / partially fixed architecturally**.
- `wasClientBefore` + VIN rules: **fixed (runtime confirmed)**.


### 23.7 Reference Dataset runtime diagnostics (2026-03-25)

**Статус:** **[confirmed]**

Что добавлено:
1. Отдельный диагностический блок `Reference Dataset / Client Lookup Diagnostics` в master-боте.
2. Разделение причин отказа lookup/dataset на дискретные статусы (`DATASET_*`, `LOOKUP_*`, `REFERENCE_DATASET_UNAVAILABLE`).
3. Диагностический lookup probe использует тот же runtime path, что WebApp existing client detection.
4. Добавлен контрольный probe по `9506275333` + ручная проверка любого номера с нормализацией.
5. В логах/диагностике фиксируются raw/normalized phone, match count, matched ids, error reason.

Подтверждённые критерии:
- можно отличить `no_match` от `dataset_unavailable` и `load_failed`; **[confirmed]**
- exact phone match rule прозрачно виден в diagnostics (`phone exact match active`); **[confirmed]**
- navigation/pending flow (`Назад`/`В меню`) сохранён; **[confirmed]**
- WebApp lookup path не дублирован отдельной «игрушечной» проверкой; **[confirmed]**

---

## 24. Runtime dataset access hardening (2026-03-27 UTC)

### 24.1 Root cause (confirmed in degraded scenario simulation)
- При ошибочном env override (`REFERENCE_CLIENT_LOOKUP_DATASET_PATH` / `REFERENCE_CLIENT_LOOKUP_SQLITE_PATH`) runtime path указывал на несуществующий файл, и lookup не стартовал (`DATASET_FILE_MISSING`), что давало `client_match_basis=reference_dataset_unavailable`. **[confirmed]**
- Для устранения неоднозначности path resolution переведён в strict-mode для explicit/env path (без fallback на другие кандидаты). Теперь проблема конфигурации/деплоя видна сразу и не маскируется. **[confirmed]**

### 24.2 Что изменено
1. `createReferenceClientLookup`:
   - strict env/explicit path resolution;
   - расширенная диагностика (`lastLookupRawPhone`, `required`, `criticalDegradation`);
   - сохранён primary rule: exact phone single match => existing client = true.
2. `/health`:
   - добавлен блок `existingClientLookup`;
   - при `REFERENCE_LOOKUP_REQUIRED=true` и недоступном dataset — `status=degraded`.
3. Master diagnostics:
   - отображаются `lookup required`, `critical degradation`, `last lookup raw phone`.

### 24.3 Runtime proof (local deploy-like)
- Dataset path в runtime: `/workspace/telegram_reviews_bot/data/reference/client_vehicle_bridge/lira_normalized_database.sqlite`; файл существует/читается, SQLite открывается, rows loaded > 0, phone index built. **[confirmed]**
- Контрольный номер `9506275333`:
  - exact match, `matchedReferenceClientId=ЦБ005355`, basis=`phone`, `existing_client=true`. **[confirmed]**
- Safety mode:
  - при `REFERENCE_LOOKUP_REQUIRED=true` + missing dataset `/health.status=degraded`. **[confirmed]**

---

## Update 2026-03-27 (UTC): Reference dataset diagnostics expansion

### Что добавлено
- Master-бот: `Диагностика -> База клиентов` расширен кнопками:
  - `Статус базы`
  - `Проверить lookup (9506275333)`
  - `Проверить lookup (9200201890)`
  - `Проверить номер`
  - `Логи базы`
- Добавлен операторский вывод runtime-контекста dataset:
  - resolved path,
  - file exists/readable,
  - loader/index status,
  - runtime cwd/main module,
  - candidate paths,
  - last lookup status/error/result.

### Root cause (подтверждение)
- Для инцидента `reference_dataset_unavailable` главным root cause остаётся mismatch runtime dataset path (env/deploy), когда сервис стартует с невалидным или недоступным SQLite-path.
- Для устранения гаданий оператор получает путь и статус открытия/чтения прямо в master-диагностике.

### Бизнес-правило
- Primary rule без изменений: exact phone match => `existing_client=true`, `client_match_basis=phone`.
- `no_match` и `dataset_unavailable` остаются строго разделёнными состояниями.

---

## 25. Deploy mismatch remediation for reference SQLite (2026-03-30 UTC)

### 25.1 Root cause
- В деградировавшем runtime зафиксировано: resolved path указывал на `/app/data/reference/client_vehicle_bridge/lira_normalized_database.sqlite`, но директория/файл отсутствовали (`DATASET_FILE_MISSING`).
- Файл присутствовал в git/repo, однако runtime `/app/data` в части deploy-сценариев не содержал reference dataset (пустой/перекрытый data-layer).

### 25.2 Что исправлено
1. **Deploy artifact hardening (Docker):**
   - dataset копируется в immutable seed path: `/opt/reference-assets/client_vehicle_bridge/lira_normalized_database.sqlite`.
2. **Startup self-check/repair:**
   - на boot выполняется проверка expected runtime path;
   - если missing/unreadable — создаётся `/app/data/reference/client_vehicle_bridge/` и выполняется copy-back из seed path;
   - логируются expected path, exists/readable, size, source copy.
3. **Lookup path consistency:**
   - WebApp flow и master diagnostics по-прежнему используют один и тот же runtime lookup entrypoint/путь.

### 25.3 Expected operational proof после deploy
- `dataset configured=yes`
- `dataset path resolved=yes`
- `runtime dataset exists=yes`
- `dataset readable=yes`
- `dataset open=ok`
- `total rows > 0`
- `phone index built=yes`
- probes:
  - `9506275333` => `exact_match`
  - `9200201890` => `exact_match`
