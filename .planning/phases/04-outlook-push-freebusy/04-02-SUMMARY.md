# Plan 04-02 Summary: Sync schema, outbox enqueue and the worker push job

## Result
**Status**: Complete
**Wave**: 2
**Agent**: engineering-backend-architect
**Completed**: 2026-10-10

## Agent Selection Rationale

| Candidate | Semantic | Heuristic | Memory | Total | Source |
|-----------|----------|-----------|--------|-------|--------|
| engineering-backend-architect | — | 15 | 4.67 | 19.67 | mandatory |
| engineering-senior-developer | — | 21 | 3.78 | 24.78 | heuristic |
| testing-qa-verification-specialist | — | 12 | 4.33 | 16.33 | heuristic |

- **Task type detected**: implementation
- **Confidence**: LOW
- **Adapter**: claude-code
- **Model tier**: sonnet

## Completed Tasks
- [x] Task 1: Migration and models (done)
- [x] Task 2: Enqueue on appointment writes (done)
- [x] Task 3: Worker push job (done)

## Files Modified
- `backend/alembic/versions/0025_outlook_sync.py`
- `backend/app/calendar_sync.py`
- `backend/app/models.py`
- `backend/app/scheduling.py`
- `backend/app/worker.py`
- `backend/tests/test_calendar_sync.py`
- `backend/tests/test_calendar_sync_schema.py`

## Verification Results
6/6 verification commands passed (run by Triad after the agent finished).

## Verification Commands
| Command | Exit Code | Result |
|---------|-----------|--------|
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_calendar_sync.py tests/test_calendar_sync_schema.py tests/test_scheduling_api.py tests/test_scheduling_schema.py tests/test_graph_calendar.py` | 0 | PASS |
| `cd backend && ruff check app tests && ruff format --check app tests` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_calendar_sync_schema.py tests/test_scheduling_schema.py` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_scheduling_api.py` | 0 | PASS |
| `cd backend && ! grep -rnE 'GraphClient\|build_client\|mail\.graph\|client\.(create_event\|update_event\|delete_event\|get_schedule)' app/scheduling.py app/routers/` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_calendar_sync.py tests/test_calendar_sync_schema.py tests/test_scheduling_api.py` | 0 | PASS |

## Key Decisions
- A claimed row is leased: `next_attempt_at` moves forward 10 minutes and the row lock is released before any Graph call. Appointment writes never wait on Graph, and a worker crash retries after the lease expires.
- The result is written under a fresh row lock. If `desired_version` changed during the push, the row stays pending; the event id, tech and generation are still saved.
- `set_org_scope` is transaction-local, so `push_pending` sets `'all'` itself before every transaction. It commits once per row.
- The old tech's email is looked up from `synced_tech_id` for deletes. A missing email gives state 'failed' with 'Tech has no email address'.
- `busy_blocks` has no ON CONFLICT or unique key beyond the id, and `status` is NOT NULL. The plan didn't specify nullability.

## Issues Encountered
- Grants on `busy_blocks` and `calendar_busy_status` follow the plan (SELECT, INSERT, UPDATE, same as `user_time_off`), so the runtime role cannot DELETE. A refresh that replaces cached blocks will need DELETE, or a different approach such as an upsert plus an expiry flag. This is a schema decision for the next wave.

## Escalations
(none)

## Handoff Context
- **Key outputs**: backend/alembic/versions/0025_outlook_sync.py; backend/app/calendar_sync.py; backend/app/models.py; backend/app/scheduling.py; backend/app/worker.py; backend/tests/test_calendar_sync.py; backend/tests/test_calendar_sync_schema.py
- **Decisions made**: A claimed row is leased: `next_attempt_at` moves forward 10 minutes and the row lock is released before any Graph call. Appointment writes never wait on Graph, and a worker crash retries after the lease expires.; The result is written under a fresh row lock. If `desired_version` changed during the push, the row stays pending; the event id, tech and generation are still saved.; `set_org_scope` is transaction-local, so `push_pending` sets `'all'` itself before every transaction. It commits once per row.; The old tech's email is looked up from `synced_tech_id` for deletes. A missing email gives state 'failed' with 'Tech has no email address'.; `busy_blocks` has no ON CONFLICT or unique key beyond the id, and `status` is NOT NULL. The plan didn't specify nullability.
- **Open questions**: (none)
- **Conventions established**: `push_pending` and `enqueue` are in `/home/user/custom-psa-nolegion/backend/app/calendar_sync.py`. `FakeCalendarClient` in `tests/test_calendar_sync.py` is a model for fake clients in later waves.; Rows sit in 'pending' while `outlook_sync_enabled` is false; enabling the setting drains them.; Backoff is min(2**attempts, 60) minutes and a row fails at 6 attempts. The create transaction id is `psa-appt-{appointment_id}-{tech_id}-{generation}`.; The free/busy plan needs `busy_blocks` DELETE, or another way to replace cached blocks (see issues). `Settings.outlook_sync_enabled` is not exposed through the API in this plan.

## Requirements Covered
- REQ-04

## Token Usage
19 requests, 1238286 input tokens (1162273 cached), 26967 output tokens, $0.6921
