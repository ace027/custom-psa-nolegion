# Plan 05-02 Summary: Client appointment emails

## Result
**Status**: Complete
**Wave**: 2
**Agent**: engineering-backend-architect
**Completed**: 2026-10-15

## Agent Selection Rationale

| Candidate | Semantic | Heuristic | Memory | Total | Source |
|-----------|----------|-----------|--------|-------|--------|
| engineering-backend-architect | — | 14 | 3.6 | 17.6 | mandatory |
| engineering-senior-developer | — | 19 | 3.78 | 22.78 | heuristic |
| testing-qa-verification-specialist | — | 12 | 4.38 | 16.38 | heuristic |

- **Task type detected**: implementation
- **Confidence**: LOW
- **Adapter**: claude-code
- **Model tier**: sonnet

## Completed Tasks
- [x] Task 1: Queue notices from scheduling (done)
- [x] Task 2: Worker send job (done)
- [x] Task 3: Tests (done)

## Files Modified
- `backend/app/client_notices.py`
- `backend/app/scheduling.py`
- `backend/app/worker.py`
- `backend/tests/test_client_notices.py`

## Verification Results
5/5 verification commands passed (run by Triad after the agent finished).

## Verification Commands
| Command | Exit Code | Result |
|---------|-----------|--------|
| `service postgresql start >/dev/null 2>&1; cd backend && ruff check app tests && ruff format --check app tests` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_client_notices.py -k queue` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_client_notices.py` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_client_notices.py tests/test_scheduling_api.py` | 0 | PASS |

## Key Decisions
- `send_due` returns the number of emails queued, not the number of rows processed. Skipped rows are not counted.
- Outbound rows are created with `auto_generated=True`, so `send_pending` adds the auto-reply headers, as autoreply and csat mail already do.
- Skipped notices are not audited. Only sent ones get an `appointment_notice.send` audit row.
- `client_notice_jobs` runs only in the mail-configured worker loop. In the idle loop (mail not configured) nothing would deliver the email, so I left it out.
- A cancelled appointment's email shows the time it was scheduled for and omits the technician.

## Issues Encountered
- The upsert's partial-index predicate must be the literal `state = 'pending'`. A bound parameter made Postgres reject the ON CONFLICT intermittently, once psycopg used a generic plan. Fixed with a literal.
- `retry_sync` still uses `appointment_view` unchanged, and it now looks up the notice itself, so that response includes `client_notice` too.

## Escalations
(none)

## Handoff Context
- **Key outputs**: backend/app/client_notices.py; backend/app/scheduling.py; backend/app/worker.py; backend/tests/test_client_notices.py
- **Decisions made**: `send_due` returns the number of emails queued, not the number of rows processed. Skipped rows are not counted.; Outbound rows are created with `auto_generated=True`, so `send_pending` adds the auto-reply headers, as autoreply and csat mail already do.; Skipped notices are not audited. Only sent ones get an `appointment_notice.send` audit row.; `client_notice_jobs` runs only in the mail-configured worker loop. In the idle loop (mail not configured) nothing would deliver the email, so I left it out.; A cancelled appointment's email shows the time it was scheduled for and omits the technician.
- **Open questions**: (none)
- **Conventions established**: `client_notices.latest_for(db, ids)` returns a `dict[int, ClientNoticeOut]` and applies RLS from the session scope.; 05-03 runs pytest against the same `psa_test` database, because `conftest` drops the schema at session start. Parallel runs could interfere with each other.

## Requirements Covered
- REQ-05

## Token Usage
26 requests, 1745597 input tokens (1571688 cached), 21293 output tokens, $0.9620
