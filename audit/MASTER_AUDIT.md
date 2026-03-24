# MASTER_AUDIT

`audit/MASTER_AUDIT.md` — единственный актуальный audit source of truth в репозитории.

## 1) Executive summary
- Node-first архитектура подтверждена: runtime строится вокруг `app.js` и `src/server/index.js`.
- Master-bot flow и status model подтверждены, включая архивную модель через `archived=true`.
- Диагностика расширена: runtime/db/channels/webapp/internal/email/workflow + отдельный AI блок.
- README-контур синхронизирован с кодом и текущей эксплуатационной моделью.
- AI проблема не скрывается: диагностика и runtime override отражаются отдельно и прозрачно.

## 2) Runtime reality
- Единый Node runtime обслуживает HTTP, webhooks, internal routes, scheduler.
- Health endpoints: `/health`, `/health/db`, `/health/max`.
- Scheduler persisted: follow-up задачи и retries живут в SQLite tasks.
- Internal routes присутствуют: `/internal/requests`, `/internal/export`, `/internal/diagnostics`, `/internal/logs`.

## 3) Bot reality
- Master bot main menu: Новые заявки, В работе, Архив, Поиск, Quality Cases, Инструкция, Диагностика, Логи, Доступы, AI (по ролям).
- Карточка заявки: Взять в работу, Запросить данные, Обработана, В сервисе, Завершить, Комментарий, Подробнее.
- Legacy callback compatibility работает через map/refresh.
- Telegram и MAX используют единый flow/status model.

## 4) WebApp reality
- Production webapp контур: `public/index.html`, `public/webapp.js`, `public/styles.css`.
- Формы доступны через `/forms/*` маршруты.
- Phone validation policy (10 digits) остаётся действующей.
- `review.html` не рассматривается как production runtime source.

## 5) Persistence reality
- SQLite — canonical persistence.
- request lifecycle fields покрывают assignment/substatus/archive/follow-up/error/rejection.
- `request_events` ведёт операционный trail.
- `tasks` хранит follow-up и retry сценарии.
- runtime info возвращает path/init/migration metadata.

## 6) Diagnostics reality
Общая диагностика покрывает:
- Runtime/health/status routes
- DB path/readiness/schema/migration hints
- Telegram/MAX readiness
- WebApp/internal routes visibility
- Email intake diagnostics (config, IMAP, folder, poll, dedupe/parse counters)
- Workflow visibility (waiting_decision/consulted follow-up)

UX поддерживает:
- краткий статус
- подробный статус
- обновить/прогнать проверку

## 7) AI diagnostics block (separate)
AI вынесен в отдельный блок, где отражаются:
- Config validation status
- Primary provider status
- Fallback status
- Runtime override present/valid
- Effective provider/model + resolution sources
- Final diagnostics verdict:
  - `CONFIG_INVALID`
  - `PRIMARY_PROVIDER_FAILED`
  - `FALLBACK_PROVIDER_FAILED`
  - `DIAGNOSTICS_OK`

## 8) Email intake block
Если email intake включён:
- IMAP enabled/config state
- connection/folder status
- last poll and result
- processed/duplicate/parse counters
- last processed email marker
- T-Business detection readiness/priority
- payload flags (`existing_client`, `needs_review`, `match_basis`, `match_confidence`)

## 9) Status/workflow block
Подтверждённая модель:
- statuses: `new`, `in_progress`, `processed`, `in_service`, `completed`, `error`
- substatuses: `recorded`, `consulted`, `spam`, `waiting_decision`, `rejected`
- archive rules: `spam`/`rejected`/`completed` -> archived
- waiting_decision requeue flow
- consulted reminder flow
- архивные заявки иммутабельны для статусных переходов в UI

## 10) Security observations
- Admin access bootstrap через env + persisted staff roles.
- Internal routes защищаются allowlist-подходом.
- Секреты маскируются в бот-диагностике и internal surfaces.
- Outbound клиентская коммуникация не использует email fallback.

## 11) Testing coverage
- Automated: `npm test` (master bot, status model, routing, persistence, AI infra, MAX/Telegram regressions и т.д.).
- Added focus: обновлённые инструкция и диагностика в master bot.
- Documentation consistency pass: README + audit сверены с runtime reality.

## 12) Known issues
- AI business usage может быть intentionally OFF при включённой AI infrastructure.
- Runtime override может присутствовать и быть invalid относительно provider/model rules.
- Internal endpoints опираются на allowlist, а не на полнофункциональный IAM.

## 13) Remaining risks
- Риск неверной интерпретации AI состояния при смешении config-invalid и provider-failed (смягчено отдельными статусами).
- Риск эксплуатационных проблем при неперсистентном/небезопасном пути SQLite.
- Риск IMAP деградации (folder/connection failures) при включённом email intake.

## 14) Recommended next checks
1. Регулярно прогонять `/diagnostics`, `/ai_diagnostics`, `/internal/diagnostics` после деплоя.
2. Ввести алерты на `CONFIG_INVALID` и provider failures отдельно.
3. Добавить периодическую сверку email-intake counters и duplicate spikes.
4. Зафиксировать runbook для needs_review/T-Business triage.
5. Усилить internal IAM, если проект выходит за текущий trusted perimeter.

---

## AI issue deep-dive (required explicit block)

### Что подтверждено
- AI diagnostics/runtime override/config resolution существуют и отображаются в admin командах.
- Доступны отдельные статусы config, primary provider, fallback provider и финальный verdict.
- Legacy env detection/ignored/used отражается в AI status/diagnostics.

### Что исправлено
- AI блок явно отделён от общей диагностики.
- Вынесены отдельные поля runtime override present/valid и effective provider/model.
- Документация приведена к модели «не смешивать config-invalid и provider-failed».

### Что не исправлено / остаётся открытым
- Нельзя гарантировать `DIAGNOSTICS_OK` без валидного окружения и доступности внешних AI провайдеров.
- При некорректных env/runtime override проблема остаётся эксплуатационной и должна лечиться конфигурацией.

### Как проверялось
- Кодовый аудит master-bot diagnostics + AI diagnostics/state resolution.
- Проверка связки config normalization -> runtime settings -> diagnostics reporting.
- Прогон автоматических тестов (`npm test`) с AI/infra сценариями.

### Текущий статус
- **partially confirmed**: архитектурно разделение и прозрачность статусов подтверждены; live provider health зависит от внешнего окружения и runtime config.
