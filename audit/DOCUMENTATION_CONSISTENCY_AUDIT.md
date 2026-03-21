# Documentation Consistency Audit

## Scope
Alignment between current code, audit files, README files, and legacy/historical documentation drift.

## Current state
- Documentation is now centralized under `readme/`.
- Audit material is now centralized under `audit/`.
- The new documentation set describes the active Node-first runtime and its SQLite-backed persistence.

## Confirmed facts
- The active production path is Node-first, not Python-first.
- The active persistence layer is SQLite, not JSON-first, though JSON import compatibility still exists.
- Telegram integration bot is Telegram-only.
- MAX is embedded in the same Node project; a separate BotHost project for MAX is not part of the documented design.
- `public/index.html` and `review.html` remain untouched.

## Risks
- Legacy Python folders can still tempt future contributors to write conflicting docs.
- Placeholder env names can still cause doc drift if someone documents aspirational architecture as current reality.
- If route behavior changes in `src/server/index.js`, static README summaries can drift again without disciplined updates.

## Gaps
- There is no automated doc-vs-code consistency test beyond broad Node structure tests.
- Machine-readable documentation is limited to `audit/MASTER_AUDIT_FOR_EXTERNAL_AI.json`.

## Legacy / dead / misleading parts
- Any prior Python-first deployment narrative is now obsolete.
- Any prior JSON-primary persistence narrative is obsolete.
- Any prior scattered README/audit files outside `readme/` and `audit/` are removed from the active contour.

## Recommendations
1. Treat this documentation set as the only source of truth for architecture and deploy guidance.
2. Update docs in the same PR as runtime changes.
3. Add a simple docs smoke test later if doc drift becomes recurrent.

## Confidence level
High.

## Follow-up checks
- Re-audit docs whenever entrypoints, persistence driver, or route maps change.
