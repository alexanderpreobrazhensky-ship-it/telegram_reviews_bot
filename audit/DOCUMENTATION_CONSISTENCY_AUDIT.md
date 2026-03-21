# Documentation consistency audit

## Summary
Prior documentation had severe doc/code drift. The most serious issue was a split-brain production contract: several files claimed that the repository was Python-first while the actual deploy path in `package.json`, `Dockerfile`, `.bothost/entrypoint.conf`, and `app.js` is Node-first.

## 1. README findings
### README files found before cleanup
- `README.md`
- `bots/client_bot/README.md`

### Problems found
- Root `README.md` was partly aligned with Node runtime, but it pointed to root-level audit/env files that were supposed to be centralized elsewhere.
- `bots/client_bot/README.md` claimed Python as the production runtime and described a webhook-first Python deploy chain that is no longer the repository's active production path.

### Action taken
- Removed README files from non-documentation locations.
- Replaced them with a centralized `readme/` contour aligned to the live code.

## 2. Audit-file findings
### Audit files found before cleanup
- `PROJECT_AUDIT.md`
- `FINAL_IMPLEMENTATION_AUDIT.md`
- `REPOSITORY_FULL_AUDIT.md`
- `ENV_FULL_AUDIT.md`
- `audit/FINAL_TECH_AUDIT.md`
- `audit/MASTER_AUDIT_FOR_EXTERNAL_AI.md`
- `audit/MASTER_AUDIT_FOR_EXTERNAL_AI.json`
- `audit/ENV_DEPLOY_REFERENCE.md`

### Problems found
- Root-level audit files violated the requirement to centralize audits under `audit/`.
- `audit/MASTER_AUDIT_FOR_EXTERNAL_AI.md` claimed there was no root Node entrypoint and described `main.py` as the deploy path, directly contradicting the code.
- `audit/FINAL_TECH_AUDIT.md` captured an earlier project state and was narrower than the current repository scope.
- `audit/ENV_DEPLOY_REFERENCE.md` and root `ENV_FULL_AUDIT.md` duplicated each other and created maintenance overlap.

### Action taken
- Removed outdated/duplicative audit files.
- Rebuilt a centralized audit contour under `audit/` with one current repository audit, one env audit, one consistency audit, and updated machine-readable summaries.

## 3. Code/doc drift still worth watching
1. `MAX_ENABLED` reads like a feature flag but does not gate MAX route registration.
2. WebApp route/state scaffolding modules are not authoritative for live routing.
3. Legacy Python env reads remain in-tree and can tempt future docs to over-document dead paths.
4. Integration env names suggest a worker architecture that does not currently exist.

## 4. Final consistency conclusion
After this cleanup, the documentation contour is aligned with the current codebase. Future drift risk remains concentrated in the legacy Python tail and in placeholder configuration names that imply more infrastructure than is currently implemented.
