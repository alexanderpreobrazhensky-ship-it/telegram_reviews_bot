# Testing

## Primary automated suite
```bash
npm test
```

## Focus areas
- master-bot menu/actions/navigation
- request status/substatus transitions
- archive immutability and legacy callback compatibility
- Telegram/MAX webhook regressions
- SQLite persistence + scheduler follow-up
- diagnostics/log visibility + masking
- AI control plane behavior (status, diagnostics, runtime switch, logs)
- internal routes (`/internal/requests`, `/internal/export`, `/internal/diagnostics`, `/internal/logs`)

## AI-specific checks (must run)
1. Valid proxy-only config path.
2. Invalid runtime override path.
3. Config mismatch detection.
4. Fallback behavior path (if configured).
5. Status vs diagnostics consistency.
6. Logs consistency (final diagnostics verdict, provider attempt/result).

## Manual smoke additions
- `/start` + full main menu traversal in master bot.
- `Назад`/`В меню` в interactive states.
- Diagnostics short/detailed/rerun.
- Email intake diagnostics (when enabled).
- README ↔ code ↔ audit consistency pass.

## Reference dataset checks (required)
После обновления bridge dataset дополнительно прогонять:
1. Repository check: файлы не в корне, структура `data/reference/client_vehicle_bridge/` корректна.
2. Dataset check: XLSX/SQLite открываются, таблицы/листы читаемы.
3. Structure check: `clients`, `vehicles`, owner linkage, mileage fields, phone/VIN assumptions.
4. Documentation check: bridge README + repo README + `audit/MASTER_AUDIT.md` согласованы.
5. Regression check: runtime тесты проходят, `app.js` и production DB path не подменены.

## Management reports test checklist
1. `Отчёты` видит только admin.
2. Не-admin получает отказ на `menu:reports` и `reports:*` callbacks.
3. Разделы отчётов открываются кнопками (без текстовых команд).
4. Периоды переключаются кнопками.
5. `Назад` / `В меню` работают из screens отчётов.
6. Проверены: summary/funnel/sources/rejections/warranty/stuck/existing_new/t_business.
7. Экспорт CSV работает и учитывает текущий reportType/period.
8. Regression: master/client/integration/webapp маршруты живы.

## Update 2026-03-25: Mandatory test matrix additions
### Dataset / Lookup
1. dataset available -> exact/no/multiple phone match.
2. dataset unavailable -> `reference_dataset_unavailable` surfaced explicitly.
3. runtime path resolution does not depend on `cwd`.
4. контрольный номер `9506275333` из reference dataset даёт `existing_client=true`, `client_match_basis=phone`.

### WebApp validation
1. `wasClientBefore=yes`, VIN empty -> allowed.
2. `wasClientBefore=no`, VIN empty -> blocked.
3. `wasClientBefore` unset -> blocked.
4. `wasClientBefore=no`, VIN set -> allowed.

### Request flow / parity
1. New WebApp request persisted with status `new`.
2. Request visible in `Новые заявки` query.
3. Telegram master notification attempted.
4. MAX master notification attempted when MAX enabled and admins configured.

## Update 2026-03-25: Reference Dataset diagnostics test matrix
Обязательные проверки:
1. dataset configured;
2. dataset missing;
3. dataset unreadable;
4. dataset load failed;
5. lookup no_match;
6. lookup exact_match;
7. lookup multiple_matches;
8. контрольный номер `9506275333`;
9. diagnostics UI в master-боте (`Диагностика -> База клиентов`);
10. pending-input flow для `Проверить номер`;
11. кнопки `Назад` / `В меню` в diagnostic flow;
12. regression: existing diagnostics/master bot/WebApp/existing-client path.
