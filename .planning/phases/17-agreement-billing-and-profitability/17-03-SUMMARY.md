# Plan 17-03 Summary: Profitability and utilisation by agreement

## Result
**Status**: Partial
**Wave**: 2
**Agent**: engineering-backend-architect
**Completed**: 2026-11-03

## Agent Selection Rationale

| Candidate | Semantic | Heuristic | Memory | Total | Source |
|-----------|----------|-----------|--------|-------|--------|
| engineering-backend-architect | — | 11 | 3.04 | 14.04 | mandatory |
| engineering-senior-developer | — | 20 | 3.02 | 23.02 | heuristic |
| testing-api-tester | — | 15 | 3.3 | 18.3 | heuristic |

- **Task type detected**: implementation
- **Confidence**: LOW
- **Adapter**: claude-code
- **Model tier**: sonnet

## Completed Tasks
- [x] Task 1: Metrics (done)
- [ ] Task 2: API and CSV (partial)
- [x] Task 3: Tests and docs (done)

## Files Modified
- `backend/app/report_metrics.py`
- `backend/app/routers/reports.py`
- `backend/tests/test_agreement_profitability.py`
- `docs/REPORTS.md`
- `docs/api/openapi.json`

## Verification Results
6/6 verification commands passed (run by Triad after the agent finished).

## Verification Commands
| Command | Exit Code | Result |
|---------|-----------|--------|
| `cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/ruff check app tests` | 0 | PASS |
| `cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/ruff format --check app tests` | 0 | PASS |
| `cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/python -m app.openapi_export --check` | 0 | PASS |
| `cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/pytest -q -p no:warnings tests/test_agreement_profitability.py tests/test_report_metrics.py tests/test_reports.py tests/test_reports_api.py` | 0 | PASS |
| `cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/pytest -q -p no:warnings tests/test_agreement_profitability.py tests/test_report_metrics.py` | 0 | PASS |
| `cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/pytest -q -p no:warnings tests/test_agreement_profitability.py` | 0 | PASS |

## Key Decisions
- the API param is named `group`; csv_for takes a separate `by` kwarg so scheduled emails, which pass the SLA group, keep the client view

## Issues Encountered
- the routes require only report:read today, not invoice:read as the plan says; left unchanged as instructed

## Escalations
| # | Severity | Type | Decision | Status | Resolution |
|---|----------|------|----------|--------|------------|
| 1 | blocker | out-of-scope-file | Approve editing backend/app/report_schemas.py (not in files_modified; the plan assumed the report schemas were in schemas.py). Add nullable `agreement_id: int / None = None`, `agreement_name: str / None = None`, `agreement_type: str / None = None` to ProfitabilityRowOut. Add `group: Literal["client","agreement"]` to ProfitabilityReportOut and UtilisationReportOut. Add `agreements: list[UtilisationAgreementRowOut] / None = None` to UtilisationReportOut; the new model has organization_id, organization_name, agreement_id, agreement_name, agreement_type, logged_minutes, billable_minutes, automation_minutes. Then regenerate docs/api/openapi.json. | pending | INVALID: type "out-of-scope-file" is not one of architecture, dependency, scope, schema, api, deletion, infrastructure, quality |

- #1 context: The metrics already return these keys and the CSVs already show them, but the FastAPI response_model strips them from the JSON. The change is additive and nullable, so it is backwards-compatible. I can apply it as a follow-up if approved.

## Handoff Context
- **Key outputs**: backend/app/report_metrics.py; backend/app/routers/reports.py; backend/tests/test_agreement_profitability.py; docs/REPORTS.md; docs/api/openapi.json
- **Decisions made**: the API param is named `group`; csv_for takes a separate `by` kwarg so scheduled emails, which pass the SLA group, keep the client view
- **Open questions**: (none)
- **Conventions established**: GET /reports/profitability?group=agreement and /utilisation?group=agreement; CSV files are profitability-by-agreement-<from>-<to>.csv and utilisation-by-agreement-...; CSV columns are client, agreement, agreement_type, then the client view's columns

## Requirements Covered
- Profitability and utilisation by agreement

## Token Usage
43 requests, 3390905 input tokens (3287742 cached), 35707 output tokens, $1.8874
