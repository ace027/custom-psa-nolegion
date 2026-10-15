# Plan 05-03 Summary: On-call API and portal appointments

## Result
**Status**: Complete
**Wave**: 2
**Agent**: engineering-senior-developer
**Completed**: 2026-10-15

## Agent Selection Rationale

| Candidate | Semantic | Heuristic | Memory | Total | Source |
|-----------|----------|-----------|--------|-------|--------|
| engineering-senior-developer | — | 19 | 3.65 | 22.65 | heuristic |
| engineering-backend-architect | — | 14 | 3.67 | 17.67 | heuristic |
| testing-qa-verification-specialist | — | 12 | 4.38 | 16.38 | heuristic |

- **Task type detected**: implementation
- **Confidence**: HIGH
- **Adapter**: claude-code
- **Model tier**: sonnet

## Completed Tasks
- [x] Task 1: On-call service and router (done)
- [x] Task 2: Portal appointments (done)
- [x] Task 3: Tests (done)

## Files Modified
- `backend/app/main.py`
- `backend/app/oncall_service.py`
- `backend/app/portal.py`
- `backend/app/routers/oncall.py`
- `backend/app/routers/portal.py`
- `backend/tests/test_oncall_api.py`
- `backend/tests/test_portal_appointments.py`

## Verification Results
5/5 verification commands passed (run by Triad after the agent finished).

## Verification Commands
| Command | Exit Code | Result |
|---------|-----------|--------|
| `service postgresql start >/dev/null 2>&1; cd backend && ruff check app tests && ruff format --check app tests` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_oncall_api.py` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_portal_appointments.py` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_oncall_api.py tests/test_portal_appointments.py tests/test_portal.py tests/test_zz_api_contract.py` | 0 | PASS |

## Key Decisions
- Invalid input (unknown or inactive users, anchor not on the handoff weekday, bad window) raises InvalidOncall, which the router returns as 422.
- Overrides accept any active user, not only rotation members. An override for a user later removed from the rotation still applies, and a test covers it.
- A schedule window of exactly 31 days is accepted; one second over is 422. start and end must carry a timezone offset.
- audit.snapshot cannot serialize time values, so oncall_service converts handoff_time to ISO text for the audit snapshot (audit.py is outside my file list).
- /now and /schedule cover active rotations only; the business timezone comes from the settings row.

## Issues Encountered
- The shared conftest reset does not truncate the oncall_* tables, so rows persisted across tests. test_oncall_api.py has an autouse fixture that truncates oncall_rotations. Adding the oncall tables to conftest TABLES would be cleaner but conftest is outside my files.
- A disabled portal answers 403 (not 401) for a signed-in contact. I tested it against /portal/me and /portal/appointments rather than assuming 401.

## Escalations
(none)

## Handoff Context
- **Key outputs**: backend/app/main.py; backend/app/oncall_service.py; backend/app/portal.py; backend/app/routers/oncall.py; backend/app/routers/portal.py; backend/tests/test_oncall_api.py; backend/tests/test_portal_appointments.py
- **Decisions made**: Invalid input (unknown or inactive users, anchor not on the handoff weekday, bad window) raises InvalidOncall, which the router returns as 422.; Overrides accept any active user, not only rotation members. An override for a user later removed from the rotation still applies, and a test covers it.; A schedule window of exactly 31 days is accepted; one second over is 422. start and end must carry a timezone offset.; audit.snapshot cannot serialize time values, so oncall_service converts handoff_time to ISO text for the audit snapshot (audit.py is outside my file list).; /now and /schedule cover active rotations only; the business timezone comes from the settings row.
- **Open questions**: (none)
- **Conventions established**: Routes: GET/POST /api/oncall/rotations, PATCH /api/oncall/rotations/{id}, GET/POST /api/oncall/rotations/{id}/overrides, DELETE /api/oncall/overrides/{id}, GET /api/oncall/now, GET /api/oncall/schedule, GET /api/portal/appointments.; oncall_service.now(ctx, at=None) and schedule(ctx, start, end) are reusable by later waves.

## Requirements Covered
- REQ-05

## Token Usage
17 requests, 970904 input tokens (755993 cached), 18927 output tokens, $0.8777
