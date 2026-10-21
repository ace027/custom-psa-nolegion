# Plan 08-03 Summary: Project billing: fixed fee up front and capped T&M

## Result
**Status**: Complete with Warnings
**Wave**: 3
**Agent**: engineering-senior-developer
**Completed**: 2026-10-21

## Agent Selection Rationale

| Candidate | Semantic | Heuristic | Memory | Total | Source |
|-----------|----------|-----------|--------|-------|--------|
| engineering-senior-developer | — | 19 | 3.12 | 22.12 | heuristic |
| testing-qa-verification-specialist | — | 15 | 3.73 | 18.73 | heuristic |
| engineering-backend-architect | — | 14 | 3.29 | 17.29 | heuristic |

- **Task type detected**: implementation
- **Confidence**: HIGH
- **Adapter**: claude-code
- **Model tier**: sonnet

## Completed Tasks
- [x] Task 1: Exclude project time from normal billing (done)
- [x] Task 2: Fixed fee and capped T&M in the run (done)
- [x] Task 3: Exact-cent tests (done)

## Files Modified
- `backend/app/reports.py`
- `backend/app/schemas.py`

## Verification Results
6/6 verification commands passed (run by Triad after the agent finished).

## Verification Commands
| Command | Exit Code | Result |
|---------|-----------|--------|
| `service postgresql start >/dev/null 2>&1; cd backend && ruff check app tests && ruff format --check app tests` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_project_billing.py tests/test_projects.py tests/test_projects_api.py tests/test_invoicing.py tests/test_block_billing.py tests/test_block_agreements.py` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q -k 'bill or invoice or run or block or proration or credit or payment'` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_invoicing.py tests/test_block_billing.py tests/test_block_agreements.py` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -c 'import app.billing'` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_project_billing.py` | 0 | PASS |

## Key Decisions
- T&M groups are sorted by (ticket number, work type id). A group whose work type has no rate is left unbilled with the existing warning, whether or not the budget has room.

## Issues Encountered
- The CSV header in backend/app/routers/reports.py is not in my file list, so revenue.csv has no 'Projects' column yet. Its subtotal and total already include project lines, so its kind columns no longer add up to the subtotal when there are project lines.

## Escalations
| # | Severity | Type | Decision | Status | Resolution |
|---|----------|------|----------|--------|------------|
| 1 | info | out-of-scope-file | Add a "projects" column (`project_cents`) to the revenue CSV in backend/app/routers/reports.py, and show `project_cents` labelled 'Projects' in frontend/src/api.ts and frontend/src/pages/billing/Reports.tsx. | pending | INVALID: type "out-of-scope-file" is not one of architecture, dependency, scope, schema, api, deletion, infrastructure, quality |
| 2 | warning | ci | Give parallel waves separate test databases (PSA_TEST_DB_NAME) in the Triad verification commands. | pending | INVALID: type "ci" is not one of architecture, dependency, scope, schema, api, deletion, infrastructure, quality |

- #1 context: The re-plan asked for the label 'Projects', but the only place a label can go is the CSV header and the frontend, both outside 08-03's files. The JSON report already returns `project_cents`.
- #2 context: tests/conftest.py drops and recreates the public schema on every session. When 08-03 and 08-04 ran tests at the same time against `psa_test`, I got errors like "relation users does not exist", which had nothing to do with this code.

## Handoff Context
- **Key outputs**: backend/app/reports.py; backend/app/schemas.py
- **Decisions made**: T&M groups are sorted by (ticket number, work type id). A group whose work type has no rate is left unbilled with the existing warning, whether or not the budget has room.
- **Open questions**: (none)
- **Conventions established**: The bill-fixed-fee route returns InvoiceOut with status 201. Errors are 409 "The fixed fee is already billed", 409 "Approve the project before billing its fee" and 409 "Only a fixed-fee project has a fee to bill".

## Requirements Covered
- REQ-08

## Token Usage
22 requests, 964350 input tokens (906401 cached), 9533 output tokens, $0.6616
