# Phase 7: Automation & API — Review Fixes

Fixes applied by the review loop, one section per cycle. Re-review decides whether each one holds.

## Cycle 1

**Date**: 2026-10-21
**Checks**: 20/20 passed
**Files changed**: `backend/alembic/versions/0028_automation_api.py`, `backend/app/automation.py`, `backend/tests/test_automation.py`

| Finding | Severity | File | Agent | Status | Notes |
|---------|----------|------|-------|--------|-------|
| F-001 | major | `backend/app/automation.py` | engineering-backend-architect | fix applied | F-001 and F-003 are fixed in the allowed files. The worker job that calls the purge and the docs retention notes could not be done because those files are outside my writable list. |
| F-003 | major | `backend/alembic/versions/0028_automation_api.py` | engineering-backend-architect | fix applied | F-001 and F-003 are fixed in the allowed files. The worker job that calls the purge and the docs retention notes could not be done because those files are outside my writable list. |

## Cycle 2

**Date**: 2026-10-21
**Checks**: 20/20 passed
**Files changed**: `backend/app/worker.py`, `backend/tests/test_automation.py`

| Finding | Severity | File | Agent | Status | Notes |
|---------|----------|------|-------|--------|-------|
| F-006 | major | `backend/app/automation.py (also backend/app/worker.py)` | engineering-senior-developer | fix applied | Added a throttled retention_jobs() to the worker. It runs at most once every 86400s and calls automation.purge_old, then commits and logs the counts. It is wired into both main() loops after webhook_jobs(). The 30-day and 90-day windows come from the env vars AUTOMATION_RUNS_RETENTION_DAYS and WEBHOOK_DELIVERIES_RETENTION_DAYS. |
