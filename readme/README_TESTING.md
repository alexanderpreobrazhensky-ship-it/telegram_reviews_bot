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
