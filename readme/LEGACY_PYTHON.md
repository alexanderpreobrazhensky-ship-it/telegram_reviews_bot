# Legacy Python contour

## Status
The Python files in this repository are **legacy/historical**, not the active production contour.

## What still exists
- `bots/client_bot/**`
- `services/client_bot_service/**`
- `shared/clients_registry.py`
- `requirements.txt`
- skipped Python tests under `tests/test_*.py`

## Why this matters
- The Python contour reads many env variables and can mislead maintainers into thinking the repo is Python-first.
- Old README and audit files previously documented Python as the production runtime even though the checked-in deploy path is Node-first.
- Historical code still has value as reference material, but it should not be used as the current operational guide.

## Current recommendation
Treat the Python contour as archive/reference until there is an explicit product decision to restore or remove it.

## If someone wants to revive it later
They should first:
1. Create a separate, explicit runtime contract.
2. Restore truthful README/audit coverage for that contour.
3. Add non-skipped tests proving the Python path actually deploys.
4. Avoid mixing Python-first and Node-first production claims in shared documentation.
