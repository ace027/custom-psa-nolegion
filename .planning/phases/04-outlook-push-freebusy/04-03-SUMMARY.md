# Plan 04-03 Summary: Free/busy cache job and the sync status, retry and availability API

## Result
**Status**: Partial
**Wave**: 3
**Agent**: engineering-backend-architect
**Completed**: 2026-10-10

## Agent Selection Rationale

| Candidate | Semantic | Heuristic | Memory | Total | Source |
|-----------|----------|-----------|--------|-------|--------|
| engineering-backend-architect | — | 17 | 4.08 | 21.08 | mandatory |
| engineering-senior-developer | — | 23 | 3.78 | 26.78 | heuristic |
| testing-qa-verification-specialist | — | 13 | 4.33 | 17.33 | heuristic |

- **Task type detected**: implementation
- **Confidence**: LOW
- **Adapter**: claude-code
- **Model tier**: sonnet

## Completed Tasks
- [x] Task 1: Busy cache refresh job (done)
- [x] Task 2: Availability and appointment sync fields (done)
- [x] Task 3: Status, retry and setting endpoints (done)

## Files Modified
(none)

## Verification Results
6/6 verification commands passed (run by Triad after the agent finished).

## Verification Commands
| Command | Exit Code | Result |
|---------|-----------|--------|
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_calendar_busy.py tests/test_calendar_sync_api.py tests/test_calendar_sync.py tests/test_scheduling_api.py tests/test_zz_api_contract.py` | 0 | PASS |
| `cd backend && ruff check app tests && ruff format --check app tests` | 0 | PASS |
| `cd backend && ! grep -rnE 'GraphClient\|build_client\|mail\.graph\|client\.(create_event\|update_event\|delete_event\|get_schedule)' app/scheduling.py app/routers/` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_calendar_busy.py` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_calendar_sync_api.py tests/test_scheduling_api.py` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_calendar_sync_api.py tests/test_zz_api_contract.py tests/test_scheduling_api.py` | 0 | PASS |

## Key Decisions
- `refresh_busy` records a missing user or a failed batch in `calendar_busy_status.last_error` and keeps the old blocks.
- `status.busy_errors` counts only polled users (active, schedule:write, has an email).
- An appointment with no sync row shows `skipped` when the setting is on.

## Issues Encountered
- `backend/alembic/versions/0025_outlook_sync.py` is modified in the working tree: the `busy_blocks` grant now includes DELETE. This is a forbidden file. I did not make the edit; it was already on disk when I started. `refresh_busy` needs the DELETE grant, so it was most likely a deliberate fix for the open question in the 04-02 handoff.
- `backend/tests/test_zz_api_contract.py` and `backend/app/routers/config.py` have no diff. The contract test passed without changes, and the settings routes already pass the new field through the schemas. I did not check how the contract test builds its route list.

## Escalations
| # | Severity | Type | Decision | Status | Resolution |
|---|----------|------|----------|--------|------------|
| 1 | warning | out-of-scope file | Accept the `GRANT SELECT, INSERT, UPDATE, DELETE ON busy_blocks` edit in `backend/alembic/versions/0025_outlook_sync.py`, or move the DELETE grant into a new migration. | pending | INVALID: type "out-of-scope file" is not one of architecture, dependency, scope, schema, api, deletion, infrastructure, quality |

- #1 context: `refresh_busy` deletes `busy_blocks` rows, so the DELETE grant is required. The migration is in the forbidden list. If 0025 was already applied anywhere, editing it will not change those databases.

## Handoff Context
- **Key outputs**: (none)
- **Decisions made**: `refresh_busy` records a missing user or a failed batch in `calendar_busy_status.last_error` and keeps the old blocks.; `status.busy_errors` counts only polled users (active, schedule:write, has an email).; An appointment with no sync row shows `skipped` when the setting is on.
- **Open questions**: (none)
- **Conventions established**: `calendar_sync.refresh_busy`, `retry` and `status_summary` are the service entry points. `busy_job` in `worker.py` holds the throttle in the module-level `_last_busy`.; `scheduling.sync_states(ctx, ids)` is the batched sync-state lookup for any new appointment list view.

## Requirements Covered
- REQ-04

## Token Usage
5 requests, 173708 input tokens (138086 cached), 2747 output tokens, $0.1441
