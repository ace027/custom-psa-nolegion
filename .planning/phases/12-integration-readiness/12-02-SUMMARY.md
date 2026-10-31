# Plan 12-02 Summary: Automation time kept out of billing; reported separately

## Result
**Status**: Complete
**Wave**: 2
**Agent**: engineering-senior-developer
**Completed**: 2026-10-31

## Agent Selection Rationale

| Candidate | Semantic | Heuristic | Memory | Total | Source |
|-----------|----------|-----------|--------|-------|--------|
| engineering-senior-developer | — | 19 | 2.83 | 21.83 | heuristic |
| testing-qa-verification-specialist | — | 15 | 3.08 | 18.08 | heuristic |
| engineering-backend-architect | — | 14 | 2.8 | 16.8 | heuristic |

- **Task type detected**: implementation
- **Confidence**: HIGH
- **Adapter**: claude-code
- **Model tier**: sonnet

## Completed Tasks
- [x] Task 1: Billing selection (done)
- [x] Task 2: Reports (done)
- [x] Task 3: Tests (done)

## Files Modified
- `backend/app/billing_repo.py`
- `backend/app/projects.py`
- `backend/app/report_metrics.py`
- `backend/app/report_schemas.py`
- `backend/app/reports.py`
- `backend/tests/test_automation_time.py`
- `docs/BILLING.md`
- `docs/REPORTS.md`

## Verification Results
8/8 verification commands passed (run by Triad after the agent finished).

## Verification Commands
| Command | Exit Code | Result |
|---------|-----------|--------|
| `service postgresql start >/dev/null 2>&1; cd backend && ruff check app tests && ruff format --check app tests` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_automation_time.py tests/test_report_metrics.py tests/test_reports_api.py tests/test_dashboards.py tests/test_isolation.py tests/test_backup_restore.py` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_billing_runs.py tests/test_block_billing.py tests/test_block_agreements.py tests/test_project_billing.py tests/test_billing_db_guards.py` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_zz_api_contract.py tests/test_permissions.py` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_billing_runs.py tests/test_block_billing.py tests/test_block_agreements.py tests/test_project_billing.py` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_report_metrics.py tests/test_reports_api.py tests/test_dashboards.py` | 0 | PASS |
| `grep -q 'automation' docs/REPORTS.md && grep -q 'utomation' docs/BILLING.md` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_automation_time.py` | 0 | PASS |

## Key Decisions
- Besides the three query filters you named, I added the labour filter to the project budget query (`projects.py`) and the unbilled report (`reports.unbilled`). Both compute money from billable minutes.
- Users with only automation minutes appear in the utilisation rows.
- Internal time still counts in logged minutes, as before.
- `dashboards.py` is unchanged. Its tiles read `logged_minutes` and `utilisation_bp`, which are now labour-only.
- The CSV column was added in `report_metrics._utilisation_csv`, not in `routers/reports.py`.

## Issues Encountered
- The 1 skipped test in `test_zz_api_contract.py` was skipped when I ran it; I did not look into why.

## Escalations
(none)

## Handoff Context
- **Key outputs**: backend/app/billing_repo.py; backend/app/projects.py; backend/app/report_metrics.py; backend/app/report_schemas.py; backend/app/reports.py; backend/tests/test_automation_time.py; docs/BILLING.md; docs/REPORTS.md
- **Decisions made**: Besides the three query filters you named, I added the labour filter to the project budget query (`projects.py`) and the unbilled report (`reports.unbilled`). Both compute money from billable minutes.; Users with only automation minutes appear in the utilisation rows.; Internal time still counts in logged minutes, as before.; `dashboards.py` is unchanged. Its tiles read `logged_minutes` and `utilisation_bp`, which are now labour-only.; The CSV column was added in `report_metrics._utilisation_csv`, not in `routers/reports.py`.
- **Open questions**: (none)
- **Conventions established**: Utilisation API rows and totals now carry `automation_minutes` (int), and the CSV's last column is `automation_minutes`. The frontend can show it.

## Requirements Covered
- REQ-14

## Token Usage
16 requests, 703396 input tokens (577761 cached), 12794 output tokens, $0.5576
