# Plan 11-01 Summary: Report metrics: SLA, utilisation, aging, profitability with CSV

## Result
**Status**: Complete
**Wave**: 1
**Agent**: data-analytics-engineer
**Completed**: 2026-10-29

## Agent Selection Rationale

| Candidate | Semantic | Heuristic | Memory | Total | Source |
|-----------|----------|-----------|--------|-------|--------|
| data-analytics-engineer | — | 17 | 0 | 17 | mandatory |
| engineering-senior-developer | — | 23 | 2.75 | 25.75 | heuristic |
| engineering-backend-architect | — | 20 | 2.75 | 22.75 | heuristic |

- **Task type detected**: implementation
- **Confidence**: LOW
- **Adapter**: claude-code
- **Model tier**: sonnet

## Completed Tasks
- [x] Task 1: Migration 0032_reporting and models (done)
- [x] Task 2: report_metrics module (done)
- [x] Task 3: Routes and admin cost rate (done)

## Files Modified
- `backend/alembic/versions/0032_reporting.py`
- `backend/app/models.py`
- `backend/app/report_metrics.py`
- `backend/app/report_schemas.py`
- `backend/app/routers/reports.py`
- `backend/app/routers/users.py`
- `backend/tests/conftest.py`
- `backend/tests/test_report_metrics.py`
- `backend/tests/test_reports_api.py`
- `backend/tests/test_seed_and_migrations.py`

## Verification Results
7/7 verification commands passed (run by Triad after the agent finished).

## Verification Commands
| Command | Exit Code | Result |
|---------|-----------|--------|
| `service postgresql start >/dev/null 2>&1; cd backend && ruff check app tests && ruff format --check app tests` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_report_metrics.py tests/test_reports_api.py tests/test_reports.py tests/test_seed_and_migrations.py tests/test_payments.py tests/test_isolation.py tests/test_backup_restore.py` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_zz_api_contract.py tests/test_permissions.py` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && ruff check app tests alembic/versions/0032_reporting.py && ruff format --check app tests alembic/versions/0032_reporting.py` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_seed_and_migrations.py` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_report_metrics.py tests/test_reports.py` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_reports_api.py tests/test_report_metrics.py tests/test_zz_api_contract.py tests/test_permissions.py` | 0 | PASS |

## Key Decisions
- Utilisation lists active staff who hold time:write, plus anyone who logged time in the range. Only approved time off reduces capacity. Every holiday date counts as a non-working day, as CONTEXT says, including short-hours holidays.
- Users with no UserWorkHours rows use the Settings business hours.
- Negative percentages in CSV are written "(12.50%)". `reports.to_csv` would prefix a leading "-" with an apostrophe as a formula guard.
- `csv_for` takes an optional `group="priority"` argument for the SLA CSV. The JSON responses also carry `range`, and the SLA response carries `group`.
- SLA counts are tallied in Python over narrow ticket columns, because the durations need per-ticket business minutes. Labour, goods, expenses and time are grouped in SQL, and `round_cents` is applied per distinct (minutes, rate) times its count.
- `utilisation` and `profitability` accept ranges of up to 60 months (inherited from `default_range`); a wide utilisation range does one pass over the working-day windows per user.

## Issues Encountered
- `audit.snapshot` serialises all user columns, so `user.update` audit rows now include `cost_rate_cents`. That is visible only to audit:read (admin). Redacting it needs `audit.py`, which is outside my files.
- The SLA percentage excludes pending and no_sla, as CONTEXT defines. The percentage's own n (met + breached) is not a separate field; consumers derive it from the counts.

## Escalations
(none)

## Handoff Context
- **Key outputs**: backend/alembic/versions/0032_reporting.py; backend/app/models.py; backend/app/report_metrics.py; backend/app/report_schemas.py; backend/app/routers/reports.py; backend/app/routers/users.py; backend/tests/conftest.py; backend/tests/test_report_metrics.py; backend/tests/test_reports_api.py; backend/tests/test_seed_and_migrations.py
- **Decisions made**: Utilisation lists active staff who hold time:write, plus anyone who logged time in the range. Only approved time off reduces capacity. Every holiday date counts as a non-working day, as CONTEXT says, including short-hours holidays.; Users with no UserWorkHours rows use the Settings business hours.; Negative percentages in CSV are written "(12.50%)". `reports.to_csv` would prefix a leading "-" with an apostrophe as a formula guard.; `csv_for` takes an optional `group="priority"` argument for the SLA CSV. The JSON responses also carry `range`, and the SLA response carries `group`.; SLA counts are tallied in Python over narrow ticket columns, because the durations need per-ticket business minutes. Labour, goods, expenses and time are grouped in SQL, and `round_cents` is applied per distinct (minutes, rate) times its count.; `utilisation` and `profitability` accept ranges of up to 60 months (inherited from `default_range`); a wide utilisation range does one pass over the working-day windows per user.
- **Open questions**: (none)
- **Conventions established**: Wave 2 can call `report_metrics.csv_for(ctx, report, start, end)`, which returns `(filename, csv)` and does not write an audit row. Only the routes call `record_export`.; Models `ReportSchedule` and `ReportScheduleRun` exist. The unique key (schedule_id, period_start) makes the worker idempotent. Valid run statuses are sent, skipped and failed.; Wave 2 should use `P.has_permission(user.role, P.REPORT_READ)` and `is_active` when picking recipients at send time.; `report_schemas.py` holds the response models. Wave 3 should add the `docs/REPORTS.md` metric dictionary by copying the `report_metrics.py` docstring.

## Requirements Covered
- REQ-11

## Token Usage
31 requests, 3274582 input tokens (3115001 cached), 54523 output tokens, $1.5672
