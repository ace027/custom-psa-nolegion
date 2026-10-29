# Plan 11-02 Summary: Role dashboards API and scheduled report emails

## Result
**Status**: Complete
**Wave**: 2
**Agent**: engineering-backend-architect
**Completed**: 2026-10-29

## Agent Selection Rationale

| Candidate | Semantic | Heuristic | Memory | Total | Source |
|-----------|----------|-----------|--------|-------|--------|
| engineering-backend-architect | — | 14 | 2.75 | 16.75 | mandatory |
| engineering-senior-developer | — | 20 | 2.75 | 22.75 | heuristic |
| testing-qa-verification-specialist | — | 14 | 3.01 | 17.009999999999998 | heuristic |

- **Task type detected**: implementation
- **Confidence**: LOW
- **Adapter**: claude-code
- **Model tier**: sonnet

## Completed Tasks
- [x] Task 1: Dashboards (done)
- [x] Task 2: Report schedules and worker emails (done)
- [x] Task 3: Schedule and dashboard routes (done)

## Files Modified
- `backend/app/dashboards.py`
- `backend/app/main.py`
- `backend/app/report_schedules.py`
- `backend/app/report_schemas.py`
- `backend/app/routers/dashboards.py`
- `backend/app/routers/reports.py`
- `backend/app/worker.py`
- `backend/tests/test_dashboards.py`
- `backend/tests/test_report_schedules.py`

## Verification Results
6/6 verification commands passed (run by Triad after the agent finished).

## Verification Commands
| Command | Exit Code | Result |
|---------|-----------|--------|
| `service postgresql start >/dev/null 2>&1; cd backend && ruff check app tests && ruff format --check app tests` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_dashboards.py tests/test_report_schedules.py tests/test_report_metrics.py tests/test_reports_api.py tests/test_notices.py` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_zz_api_contract.py tests/test_permissions.py` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_dashboards.py` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_report_schedules.py` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_report_schedules.py tests/test_dashboards.py tests/test_zz_api_contract.py` | 0 | PASS |

## Key Decisions
- "Last 30 days" for `sla_30d` is today minus 29 days through today. Month-to-date runs from the 1st of the month through today. Last week is the previous Monday to Sunday.
- `run_due` locks the active schedule rows with `FOR UPDATE SKIP LOCKED`, so two workers cannot both email the same period.
- A failed run is recorded and not retried in the same period. This follows from the unique key on (schedule_id, period_start), and a skipped run behaves the same way.
- PATCH only re-checks recipients when `recipient_user_ids` is in the request. A deactivated schedule can still be renamed or deactivated after a recipient loses report:read.
- On a frequency change, the other frequency's field is cleared. Switching weekly to monthly without `day_of_month` returns 409.
- `report_schedules` calls `report_metrics.csv_for` through the module, so tests can patch it. Each send also writes an audit row, `report_schedule.send`.

## Issues Encountered
- A run with status "sent" means the email is queued as pending, as with `send_notice`. Delivery happens when the mail worker next sends. Unlike `send_notice`, I did not refuse to queue when the mailbox is unconfigured, because the worker runs idle in that state.
- The git status shows `.planning/memory/PREFERENCES.md` as modified. I did not touch it.

## Escalations
(none)

## Handoff Context
- **Key outputs**: backend/app/dashboards.py; backend/app/main.py; backend/app/report_schedules.py; backend/app/report_schemas.py; backend/app/routers/dashboards.py; backend/app/routers/reports.py; backend/app/worker.py; backend/tests/test_dashboards.py; backend/tests/test_report_schedules.py
- **Decisions made**: "Last 30 days" for `sla_30d` is today minus 29 days through today. Month-to-date runs from the 1st of the month through today. Last week is the previous Monday to Sunday.; `run_due` locks the active schedule rows with `FOR UPDATE SKIP LOCKED`, so two workers cannot both email the same period.; A failed run is recorded and not retried in the same period. This follows from the unique key on (schedule_id, period_start), and a skipped run behaves the same way.; PATCH only re-checks recipients when `recipient_user_ids` is in the request. A deactivated schedule can still be renamed or deactivated after a recipient loses report:read.; On a frequency change, the other frequency's field is cleared. Switching weekly to monthly without `day_of_month` returns 409.; `report_schedules` calls `report_metrics.csv_for` through the module, so tests can patch it. Each send also writes an audit row, `report_schedule.send`.
- **Open questions**: (none)
- **Conventions established**: Wave 3 can use `GET/POST /api/reports/schedules`, `PATCH /api/reports/schedules/{id}` and `GET /api/reports/schedules/{id}/runs`. The payload shapes are `ScheduleIn`, `ScheduleUpdate`, `ScheduleOut` and `ScheduleRunOut` in `report_schemas.py`.; `GET /api/dashboard/me` returns `MyDashboardOut`, and `GET /api/reports/dashboard` returns `ManagerDashboardOut`.; Schedules can be read with report:read but only written with config:manage. Billing therefore gets 403 on POST and PATCH.; The 409 messages for recipient errors name the user, for example "<display name> cannot read reports (needs report:read)".; The aging CSV ignores the period and is as of the run date. The email body says so.

## Requirements Covered
- REQ-11

## Token Usage
28 requests, 2197896 input tokens (2091705 cached), 32328 output tokens, $1.0071
