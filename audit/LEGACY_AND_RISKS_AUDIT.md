# Legacy and risk audit

## 1. Legacy contour assessment
### Legacy Python contour
The Python client-bot/service files remain in the repository as historical assets. They are large, env-heavy, and previously had README support that made them look current. They are no longer part of the active production path.

### Legacy deploy traces
- `requirements.txt` still exists.
- skipped Python tests still exist.
- historical config aliases still exist in Python code.
- `legacy/index.js` remains as a non-production shim.

### What still influences the project
- Repository complexity and onboarding overhead.
- Env naming confusion.
- Documentation drift risk.

## 2. Technical debt
### High-priority debt
1. Replace JSON persistence with a real DB if growth is expected.
2. Add auth/verification to manual/email/1C HTTP routes.
3. Separate scheduler/worker concerns from the HTTP process.

### Medium-priority debt
1. Unify authoritative route declarations.
2. Add better live smoke automation.
3. Resolve MAX parity gaps.
4. Decide whether to archive or remove the Python contour.

### Low-priority debt
1. Tighten naming around legacy/declarative env.
2. Reduce scaffolding modules that are not on the live path.

## 3. Operational risk audit
### Highest current operational risks
- Loss of JSON DB persistence on redeploy.
- Silent or confusing recovery from corrupted DB content.
- Exposed integration endpoints without auth.
- Duplicate scheduler processing if more than one instance runs.

### Moderate operational risks
- Restart-sensitive in-memory client-bot sessions.
- MAX live behavior still requiring manual validation.
- Role bootstrap depending on env quality.

## 4. Further development readiness
### Good news
- The Node runtime core is understandable.
- Shared services allow Telegram and MAX to reuse most logic.
- Reporting and source tracking are already broad enough to support future enhancement.

### Constraints
- Scale architecture is not ready.
- Security hardening is incomplete.
- Legacy tails consume attention and documentation bandwidth.

## 5. Overall conclusion
The project is ready for continued incremental development **if maintainers treat the Node contour as canonical** and address persistence/security debt before broadening the deploy footprint.
