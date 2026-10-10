# Plan 04-03 Summary: Free/busy cache job and the sync status, retry and availability API

## Result
**Status**: BLOCKED
**Wave**: 3
**Agent**: engineering-backend-architect
**Completed**: 2026-10-10
**Failure Class**: BLOCKER — $ service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_calendar_busy.py tests/test_calendar_sync_api.py tests/test_calendar_sync.py tests/test_scheduling_api.py tests

## Agent Selection Rationale

| Candidate | Semantic | Heuristic | Memory | Total | Source |
|-----------|----------|-----------|--------|-------|--------|
| engineering-backend-architect | — | 17 | 4.67 | 21.67 | mandatory |
| engineering-senior-developer | — | 23 | 3.78 | 26.78 | heuristic |
| testing-qa-verification-specialist | — | 13 | 4.33 | 17.33 | heuristic |

- **Task type detected**: implementation
- **Confidence**: LOW
- **Adapter**: claude-code
- **Model tier**: sonnet

## Completed Tasks
- [ ] Task 1: Busy cache refresh job (partial)
- [x] Task 2: Availability and appointment sync fields (done)
- [x] Task 3: Status, retry and setting endpoints (done)

## Files Modified
- `backend/app/calendar_sync.py`
- `backend/app/routers/scheduling.py`
- `backend/app/scheduling.py`
- `backend/app/scheduling_schemas.py`
- `backend/app/schemas.py`
- `backend/app/worker.py`
- `backend/tests/test_calendar_busy.py`
- `backend/tests/test_calendar_sync_api.py`
- `docs/SCHEDULING.md`

## Verification Results
4/6 verification commands passed (run by Triad after the agent finished).

## Verification Commands
| Command | Exit Code | Result |
|---------|-----------|--------|
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_calendar_busy.py tests/test_calendar_sync_api.py tests/test_calendar_sync.py tests/test_scheduling_api.py tests/test_zz_api_contract.py` | 1 | FAIL |
| `cd backend && ruff check app tests && ruff format --check app tests` | 0 | PASS |
| `cd backend && ! grep -rnE 'GraphClient\|build_client\|mail\.graph\|client\.(create_event\|update_event\|delete_event\|get_schedule)' app/scheduling.py app/routers/` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_calendar_busy.py` | 1 | FAIL |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_calendar_sync_api.py tests/test_scheduling_api.py` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_calendar_sync_api.py tests/test_zz_api_contract.py tests/test_scheduling_api.py` | 0 | PASS |

## Key Decisions
- routers/config.py and tests/test_zz_api_contract.py are unchanged. update_settings sets attributes generically, so the schema change is enough. The contract tests already cover the new routes.
- An appointment with no appointment_sync row shows sync state 'skipped' when the setting is enabled.
- busy_fetched_at and busy_errors count only users who are still polled (active, schedule:write role, with an email).
- A "retry outside scope gives 404" test calls the service directly with Scope.orgs. HTTP staff requests always use Scope.all(), so that case cannot happen over HTTP.

## Issues Encountered
- busy_blocks DELETE is not granted to psa_app, so refresh_busy fails in production as well as in tests.
- Blocked: Needs a new migration in backend/alembic/ (forbidden) to grant DELETE on busy_blocks to psa_app.
- BLOCKER: $ service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_calendar_busy.py tests/test_calendar_sync_api.py tests/test_calendar_sync.py tests/test_scheduling_api.py tests

## Escalations
| # | Severity | Type | Decision | Status | Resolution |
|---|----------|------|----------|--------|------------|
| 1 | blocker | schema | Add migration 0026 granting DELETE on busy_blocks to the app role (psa_app). | pending |  |
| 2 | blocker | api | Resolve: $ service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_calendar_busy.py tests/test_calendar_sync_api.py tests/test_calendar_sync.py tests/test_scheduling_api.py tests | pending |  |

- #1 context: The plan says to delete a user's busy_blocks and insert the new ones. Migration 0025 granted only SELECT, INSERT, UPDATE on busy_blocks, so every refresh that finds existing blocks fails with permission denied. The alternative is a workaround that reuses rows and parks leftover rows as dummy blocks, which I do not recommend. Once the grant exists, no code change is needed. A different replacement approach (such as a stale marker column) would also need a migration.
- #2 context: Verification failed (service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_calendar_busy.py tests/test_calendar_sync_api.py tests/test_calendar_sync.py tests/test_scheduling_api.py tests/test_zz_api_contract.py; service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_calendar_busy.py); a BLOCKER is not auto-fixed.

## Handoff Context
- **Key outputs**: backend/app/calendar_sync.py; backend/app/routers/scheduling.py; backend/app/scheduling.py; backend/app/scheduling_schemas.py; backend/app/schemas.py; backend/app/worker.py; backend/tests/test_calendar_busy.py; backend/tests/test_calendar_sync_api.py; docs/SCHEDULING.md
- **Decisions made**: routers/config.py and tests/test_zz_api_contract.py are unchanged. update_settings sets attributes generically, so the schema change is enough. The contract tests already cover the new routes.; An appointment with no appointment_sync row shows sync state 'skipped' when the setting is enabled.; busy_fetched_at and busy_errors count only users who are still polled (active, schedule:write role, with an email).; A "retry outside scope gives 404" test calls the service directly with Scope.orgs. HTTP staff requests always use Scope.all(), so that case cannot happen over HTTP.
- **Open questions**: (none)
- **Conventions established**: Add a migration after 0025 (e.g. 0026) with GRANT DELETE ON busy_blocks TO psa_app. Rerun the verification afterward.; appointment_views preloads orgs, tickets and techs and holds the rows in a local list, because the SQLAlchemy identity map is weak.; The availability response now includes outlook_busy and outlook_fetched_at, and each appointment includes sync, for the frontend.

## Requirements Covered
- REQ-04

### Failed verification output
`service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_calendar_busy.py tests/test_calendar_sync_api.py tests/test_calendar_sync.py tests/test_scheduling_api.py tests/test_zz_api_contract.py`
```
 'dev'} request_id=bfde67f107bc4b5ca9472236c404950e ip=testclient
2026-10-10 15:45:26,354 INFO httpx2 HTTP Request: POST http://testserver/api/auth/dev-login "HTTP/1.1 200 OK"
2026-10-10 15:45:26,365 INFO psa.auth auth_event action=auth.login user_id=2 detail={'method': 'dev'} request_id=b812e2473f8c4b64a3fa0e0e03775020 ip=testclient
2026-10-10 15:45:26,370 INFO httpx2 HTTP Request: POST http://testserver/api/auth/dev-login "HTTP/1.1 200 OK"
------------------------------ Captured log call -------------------------------
INFO     psa.auth:audit.py:72 auth_event action=auth.login user_id=1 detail={'method': 'dev'} request_id=bfde67f107bc4b5ca9472236c404950e ip=testclient
INFO     httpx2:_client.py:1085 HTTP Request: POST http://testserver/api/auth/dev-login "HTTP/1.1 200 OK"
INFO     psa.auth:audit.py:72 auth_event action=auth.login user_id=2 detail={'method': 'dev'} request_id=b812e2473f8c4b64a3fa0e0e03775020 ip=testclient
INFO     httpx2:_client.py:1085 HTTP Request: POST http://testserver/api/auth/dev-login "HTTP/1.1 200 OK"
=========================== short test summary info ============================
FAILED tests/test_calendar_busy.py::test_blocks_replace_old_ones - sqlalchemy...
FAILED tests/test_calendar_busy.py::test_batches_of_twenty - sqlalchemy.exc.P...
FAILED tests/test_calendar_busy.py::test_graph_error_keeps_old_blocks_and_records_it
FAILED tests/test_calendar_busy.py::test_missing_user_keeps_blocks_while_others_refresh
4 failed, 61 passed, 1 skipped in 37.69s

```
`service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_calendar_busy.py`
```
il={'method': 'dev'} request_id=788f48f643a2475f809b9aad1f0d631c ip=testclient
2026-10-10 15:46:06,957 INFO httpx2 HTTP Request: POST http://testserver/api/auth/dev-login "HTTP/1.1 200 OK"
2026-10-10 15:46:06,968 INFO psa.auth auth_event action=auth.login user_id=2 detail={'method': 'dev'} request_id=36f2df832be74b9aa564ccfafd4cef9d ip=testclient
2026-10-10 15:46:06,972 INFO httpx2 HTTP Request: POST http://testserver/api/auth/dev-login "HTTP/1.1 200 OK"
------------------------------ Captured log call -------------------------------
INFO     psa.auth:audit.py:72 auth_event action=auth.login user_id=1 detail={'method': 'dev'} request_id=788f48f643a2475f809b9aad1f0d631c ip=testclient
INFO     httpx2:_client.py:1085 HTTP Request: POST http://testserver/api/auth/dev-login "HTTP/1.1 200 OK"
INFO     psa.auth:audit.py:72 auth_event action=auth.login user_id=2 detail={'method': 'dev'} request_id=36f2df832be74b9aa564ccfafd4cef9d ip=testclient
INFO     httpx2:_client.py:1085 HTTP Request: POST http://testserver/api/auth/dev-login "HTTP/1.1 200 OK"
=========================== short test summary info ============================
FAILED tests/test_calendar_busy.py::test_blocks_replace_old_ones - sqlalchemy...
FAILED tests/test_calendar_busy.py::test_batches_of_twenty - sqlalchemy.exc.P...
FAILED tests/test_calendar_busy.py::test_graph_error_keeps_old_blocks_and_records_it
FAILED tests/test_calendar_busy.py::test_missing_user_keeps_blocks_while_others_refresh
4 failed, 4 passed in 5.09s

```

## Token Usage
30 requests, 2079726 input tokens (1994083 cached), 28743 output tokens, $0.9003
