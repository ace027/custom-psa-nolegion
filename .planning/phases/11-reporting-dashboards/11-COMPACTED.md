---
phase: 11-reporting-dashboards
compacted: 2026-10-29
original_summaries: [11-01-SUMMARY.md, 11-02-SUMMARY.md, 11-03-SUMMARY.md]
requirements_satisfied: [REQ-11]
---

# Phase 11: Reporting & dashboards — Compacted Summary

## Deliverables
- 11-01 Report metrics: SLA, utilisation, aging, profitability with CSV (Complete): backend/alembic/versions/0032_reporting.py, backend/app/models.py, backend/app/report_metrics.py, backend/app/report_schemas.py, backend/app/routers/reports.py, backend/app/routers/users.py, backend/tests/conftest.py, backend/tests/test_report_metrics.py, backend/tests/test_reports_api.py, backend/tests/test_seed_and_migrations.py
- 11-02 Role dashboards API and scheduled report emails (Complete): backend/app/dashboards.py, backend/app/main.py, backend/app/report_schedules.py, backend/app/report_schemas.py, backend/app/routers/dashboards.py, backend/app/routers/reports.py, backend/app/worker.py, backend/tests/test_dashboards.py, backend/tests/test_report_schedules.py
- 11-03 Report pages, role dashboards UI, cost rates and docs (Complete): docs/REPORTS.md, docs/verify/reports.md, frontend/src/App.tsx, frontend/src/Dashboards.test.tsx, frontend/src/api.ts, frontend/src/pages/Dashboard.tsx, frontend/src/pages/Users.tsx, frontend/src/pages/reports/AgingReport.tsx, frontend/src/pages/reports/ProfitabilityReport.tsx, frontend/src/pages/reports/ReportSchedules.tsx, frontend/src/pages/reports/SlaReport.tsx, frontend/src/pages/reports/UtilisationReport.tsx

## Decisions
- 11-01: Utilisation lists active staff who hold time:write, plus anyone who logged time in the range. Only approved time off reduces capacity. Every holiday date counts
- 11-01: Users with no UserWorkHours rows use the Settings business hours.
- 11-01: Negative percentages in CSV are written "(12.50%)". `reports.to_csv` would prefix a leading "-" with an apostrophe as a formula guard.
- 11-02: "Last 30 days" for `sla_30d` is today minus 29 days through today. Month-to-date runs from the 1st of the month through today. Last week is the previous Monday 
- 11-02: `run_due` locks the active schedule rows with `FOR UPDATE SKIP LOCKED`, so two workers cannot both email the same period.
- 11-02: A failed run is recorded and not retried in the same period. This follows from the unique key on (schedule_id, period_start), and a skipped run behaves the same
- 11-03: Recipients are picked from active users with role admin or billing, because the user list has no permissions. The server still checks every recipient.
- 11-03: A null percentage shows as "-" with no n, per the plan. Utilisation shows n as capacity minutes.
- 11-03: The report pages default to this month, so the CSV link carries `from` and `to` (plus `group` for SLA).

## Conventions and Open Questions
- 11-01 convention: Wave 2 can call `report_metrics.csv_for(ctx, report, start, end)`, which returns `(filename, csv)` and does not write an audit row. Only the routes call `record
- 11-01 convention: Models `ReportSchedule` and `ReportScheduleRun` exist. The unique key (schedule_id, period_start) makes the worker idempotent. Valid run statuses are sent, skip
- 11-01 convention: Wave 2 should use `P.has_permission(user.role, P.REPORT_READ)` and `is_active` when picking recipients at send time.
- 11-02 convention: Wave 3 can use `GET/POST /api/reports/schedules`, `PATCH /api/reports/schedules/{id}` and `GET /api/reports/schedules/{id}/runs`. The payload shapes are `Schedu
- 11-02 convention: `GET /api/dashboard/me` returns `MyDashboardOut`, and `GET /api/reports/dashboard` returns `ManagerDashboardOut`.
- 11-02 convention: Schedules can be read with report:read but only written with config:manage. Billing therefore gets 403 on POST and PATCH.
- 11-03 convention: Shared helpers for report pages: `useRange`, `PctBar`, `dl` and `num` are exported from `pages/reports/SlaReport.tsx`
- 11-03 convention: `pctN`, `hm`, `thisMonth` and `reportsApi` are in `api.ts`.
- 11-03 convention: The cost rate is reachable only through `getCostRate` and `putCostRate`, called from the admin form in Users.tsx.

## Files Modified
| File | Change |
|------|--------|
| `backend/alembic/versions/0032_reporting.py` | 11-01: Report metrics: SLA, utilisation, aging, profitability with CSV |
| `backend/app/models.py` | 11-01: Report metrics: SLA, utilisation, aging, profitability with CSV |
| `backend/app/report_metrics.py` | 11-01: Report metrics: SLA, utilisation, aging, profitability with CSV |
| `backend/app/report_schemas.py` | 11-01: Report metrics: SLA, utilisation, aging, profitability with CSV |
| `backend/app/routers/reports.py` | 11-01: Report metrics: SLA, utilisation, aging, profitability with CSV |
| `backend/app/routers/users.py` | 11-01: Report metrics: SLA, utilisation, aging, profitability with CSV |
| `backend/tests/conftest.py` | 11-01: Report metrics: SLA, utilisation, aging, profitability with CSV |
| `backend/tests/test_report_metrics.py` | 11-01: Report metrics: SLA, utilisation, aging, profitability with CSV |
| `backend/tests/test_reports_api.py` | 11-01: Report metrics: SLA, utilisation, aging, profitability with CSV |
| `backend/tests/test_seed_and_migrations.py` | 11-01: Report metrics: SLA, utilisation, aging, profitability with CSV |
| `backend/app/dashboards.py` | 11-02: Role dashboards API and scheduled report emails |
| `backend/app/main.py` | 11-02: Role dashboards API and scheduled report emails |
| `backend/app/report_schedules.py` | 11-02: Role dashboards API and scheduled report emails |
| `backend/app/report_schemas.py` | 11-02: Role dashboards API and scheduled report emails |
| `backend/app/routers/dashboards.py` | 11-02: Role dashboards API and scheduled report emails |
| `backend/app/routers/reports.py` | 11-02: Role dashboards API and scheduled report emails |
| `backend/app/worker.py` | 11-02: Role dashboards API and scheduled report emails |
| `backend/tests/test_dashboards.py` | 11-02: Role dashboards API and scheduled report emails |
| `backend/tests/test_report_schedules.py` | 11-02: Role dashboards API and scheduled report emails |
| `docs/REPORTS.md` | 11-03: Report pages, role dashboards UI, cost rates and docs |
| `docs/verify/reports.md` | 11-03: Report pages, role dashboards UI, cost rates and docs |
| `frontend/src/App.tsx` | 11-03: Report pages, role dashboards UI, cost rates and docs |
| `frontend/src/Dashboards.test.tsx` | 11-03: Report pages, role dashboards UI, cost rates and docs |
| `frontend/src/api.ts` | 11-03: Report pages, role dashboards UI, cost rates and docs |
| `frontend/src/pages/Dashboard.tsx` | 11-03: Report pages, role dashboards UI, cost rates and docs |
| `frontend/src/pages/Users.tsx` | 11-03: Report pages, role dashboards UI, cost rates and docs |
| `frontend/src/pages/reports/AgingReport.tsx` | 11-03: Report pages, role dashboards UI, cost rates and docs |
| `frontend/src/pages/reports/ProfitabilityReport.tsx` | 11-03: Report pages, role dashboards UI, cost rates and docs |
| `frontend/src/pages/reports/ReportSchedules.tsx` | 11-03: Report pages, role dashboards UI, cost rates and docs |
| `frontend/src/pages/reports/SlaReport.tsx` | 11-03: Report pages, role dashboards UI, cost rates and docs |
| `frontend/src/pages/reports/UtilisationReport.tsx` | 11-03: Report pages, role dashboards UI, cost rates and docs |

## Verification
- 11-01 (REQ-11): 7/7 verification commands passed
- 11-02 (REQ-11): 6/6 verification commands passed
- 11-03 (REQ-11): 5/5 verification commands passed

## Agents
- 11-01: data-analytics-engineer
- 11-02: engineering-backend-architect
- 11-03: engineering-frontend-developer

## Also Covered
- .planning/VERIFY.md
