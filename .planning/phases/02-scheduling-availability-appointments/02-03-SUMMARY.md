# Plan 02-03 Summary: Scheduling services and API

## Result
**Status**: Complete
**Wave**: 2
**Agent**: engineering-senior-developer (opus)
**Completed**: 2026-10-09

## Completed Tasks
- [x] Task 1: Schemas and service (done)
- [x] Task 2: Routes (done)
- [x] Task 3: API tests and docs (done)

## Files Modified
- `backend/app/scheduling.py`
- `backend/app/scheduling_schemas.py`
- `backend/app/routers/scheduling.py`
- `backend/app/main.py`
- `backend/tests/test_scheduling_api.py`
- `docs/SCHEDULING.md`

## Verification Results
A worker restart interrupted the executor after the agent answered, so the orchestrator ran verification by hand:
- `ruff check app tests && ruff format --check app tests`: PASS
- `python -m pytest -q tests/test_scheduling_api.py tests/test_scheduling_schema.py tests/test_availability.py`: 55 passed
- Full suite (`python -m pytest -q`): 831 passed, 1 failed. `test_downgrade_refuses_while_block_agreements_exist` hardcoded head "0023"; it now compares against the head recorded before the downgrade (fixed in a follow-up commit). The rerun passes.

## Orchestrator review (auth/permissions, main model)
- Schedule read/write: self, or a holder of timeoff:approve. Time off for someone else and approve/reject: admins only. Cancel: owner or admin.
- Appointment lookups, updates and conflict queries go through Scope on organization_id; ticket lookup is scoped.
- The time-off reason is redacted for viewers who are neither the owner nor an approver.
