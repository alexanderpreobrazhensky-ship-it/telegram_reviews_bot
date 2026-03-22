# Documentation Consistency Audit

## Scope
Consistency between current code, audit files, and `readme/` documentation, with emphasis on eliminating outdated architectural descriptions.

## Current state
- The documentation set now consistently describes the project as Node-first, SQLite-backed, and centered on `app.js` + `src/server/index.js`.
- Audit files live under `audit/`; operational docs live under `readme/`.
- The refreshed audit set uses consistent terminology for Telegram, MAX, WebApp, persistence, runtime, and security.

## Confirmed facts
### Confirmed by direct repo inspection
- `readme/README_DEPLOY.md`, `README_RUNTIME.md`, `README_ENV.md`, `README_PERSISTENCE.md`, `README_WEBAPP.md`, and `README_MAX.md` all align with the active Node-first runtime.
- The refreshed audit files now align with the code-confirmed reality that SQLite is active and JSON is compatibility-only.
- Telegram integration bot is consistently described as Telegram-only.
- MAX is consistently described as embedded in the same Node project, not as a separate deployment.
- `review.html` and `public/index.html` were left untouched.

### Previously stale claims removed or downgraded
- Python-first production descriptions.
- JSON-first persistence descriptions.
- Blanket statements that MAX is purely unimplemented.
- Blanket statements that older phone-input issues are still confirmed production facts.
- Claims that route maps outside `src/server/index.js` are authoritative.

## What changed after modernization
- Documentation now follows the current runtime path instead of the broad historical tree.
- Audit files now distinguish code-confirmed facts from runtime-only assumptions.
- Terminology is synchronized across repository, env, runtime, persistence, WebApp, Telegram, MAX, security, testing, and post-deploy audits.
- The external-agent starter document is now the Markdown file `audit/MASTER_AUDIT_FOR_EXTERNAL_AI.md`.

## Remaining gaps
- The machine-readable JSON mirror previously present under `audit/` could drift if maintained separately.
- There is still no automated doc-vs-code consistency test.
- Legacy repository folders can still attract future documentation drift if someone documents from a superficial tree scan.

## Risks
- If future runtime changes land without parallel audit/readme updates, drift can reappear quickly.
- Legacy and placeholder files/env names still create documentation ambiguity.
- Operators may still rely on old external notes not stored in the repo.

## Legacy / dead / misleading parts
- Any document describing the project as Python-first or legacy-first is stale.
- Any document describing JSON as the current primary production store is stale.
- Any document that generalizes session-specific WebApp issues into repo-wide production blockers without evidence is misleading.
- The older JSON-form external-agent audit mirror is no longer needed as a primary source of truth.

## Confidence level
High for repository-internal documentation consistency after this rewrite; medium for external/off-repo documentation because it was not inspected.

## Recommended follow-up checks
- Remove or regenerate any machine-readable audit mirror if you want to keep only one external-agent source of truth.
- Update audit/readme files in the same PR whenever runtime or env behavior changes.
- Consider adding a lightweight CI check that confirms required audit files exist only under `audit/`.
