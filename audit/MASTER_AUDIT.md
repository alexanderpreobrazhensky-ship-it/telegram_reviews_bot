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

