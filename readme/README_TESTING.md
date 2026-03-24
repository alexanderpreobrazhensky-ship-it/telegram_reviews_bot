# Testing

## Primary suite
```bash
npm test
```

## Coverage focus
- master-bot menu routing and callback handling
- request card actions and state transitions
- legacy callback compatibility
- SQLite persistence and follow-up tasks
- Telegram and MAX webhook behavior
- diagnostics/log masking
- AI-ready config loading without runtime enablement


## AI Stage 1 tests
- Config parsing for AI env defaults and overrides.
- AI runtime settings override and validation tests.
- AI service fallback and business-usage-disabled behavior tests.
- Master bot admin-only AI commands tests.
