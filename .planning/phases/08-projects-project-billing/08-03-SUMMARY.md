# Plan 08-03 Summary: Project billing: fixed fee up front and capped T&M

## Result
**Status**: Partial
**Wave**: 3
**Agent**: engineering-senior-developer
**Completed**: 2026-10-21
**Failure Class**: BLOCKER — $ service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_project_billing.py tests/test_projects.py tests/test_projects_api.py tests/test_invoicing.py tests/test_block_b

## Agent Selection Rationale

| Candidate | Semantic | Heuristic | Memory | Total | Source |
|-----------|----------|-----------|--------|-------|--------|
| engineering-senior-developer | — | 19 | 3.08 | 22.08 | heuristic |
| testing-qa-verification-specialist | — | 15 | 3.73 | 18.73 | heuristic |
| engineering-backend-architect | — | 14 | 3.25 | 17.25 | heuristic |

- **Task type detected**: implementation
- **Confidence**: HIGH
- **Adapter**: claude-code
- **Model tier**: sonnet

## Completed Tasks
- [x] Task 1: Exclude project time from normal billing (done)
- [x] Task 2: Fixed fee and capped T&M in the run (done)
- [ ] Task 3: Exact-cent tests (partial)

## Files Modified
- `backend/app/billing.py`
- `backend/app/billing_repo.py`
- `backend/app/routers/projects.py`
- `backend/tests/test_project_billing.py`

## Verification Results
3/6 verification commands passed (run by Triad after the agent finished).

## Verification Commands
| Command | Exit Code | Result |
|---------|-----------|--------|
| `service postgresql start >/dev/null 2>&1; cd backend && ruff check app tests && ruff format --check app tests` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_project_billing.py tests/test_projects.py tests/test_projects_api.py tests/test_invoicing.py tests/test_block_billing.py tests/test_block_agreements.py` | 1 | FAIL |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q -k 'bill or invoice or run or block or proration or credit or payment'` | 1 | FAIL |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_invoicing.py tests/test_block_billing.py tests/test_block_agreements.py` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -c 'import app.billing'` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_project_billing.py` | 1 | FAIL |

## Key Decisions
- billable project = active, on_hold or completed, or cancelled with approved_at set; no approved_at date filter, so the fee goes on the next run created after approval

## Issues Encountered
- app/schemas.py:774 LineKind needs "project" (blocks invoice reads); app/reports.py KINDS needs "project" or the revenue report will raise KeyError once a project line is finalized (not tested)
- BLOCKER: $ service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_project_billing.py tests/test_projects.py tests/test_projects_api.py tests/test_invoicing.py tests/test_block_b

## Escalations
| # | Severity | Type | Decision | Status | Resolution |
|---|----------|------|----------|--------|------------|
| 1 | blocker | out-of-scope-file / api-contract | Add "project" to LineKind in backend/app/schemas.py (and optionally expose project_id on LineOut). Add "project" to KINDS in backend/app/reports.py, or map it to an existing revenue bucket. | pending | INVALID: type "out-of-scope-file / api-contract" is not one of architecture, dependency, scope, schema, api, deletion, infrastructure, quality |
| 2 | warning | scope | /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/linekind_plugin.py is not in files_modified of plan 08-03. Allowed under control mode guarded and recorded as an escalation; stay inside the plan's files unless the task cannot be done otherwise. | pending |  |
| 3 | blocker | api | Resolve: $ service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_project_billing.py tests/test_projects.py tests/test_projects_api.py tests/test_invoicing.py tests/test_block_b | pending |  |

- #1 context: Migration 0029 added the 'project' line kind, but the response schema and the revenue report were not updated. Every invoice with a project line returns 500 on read. Neither file is in plan 08-03's write list. With the LineKind fix, all 17 project billing tests pass.
- #3 context: Verification failed (service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_project_billing.py tests/test_projects.py tests/test_projects_api.py tests/test_invoicing.py tests/test_block_billing.py tests/test_block_agreements.py; service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q -k 'bill or invoice or run or block or proration or credit or payment'; service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_project_billing.py); a BLOCKER is not auto-fixed.

## Handoff Context
- **Key outputs**: backend/app/billing.py; backend/app/billing_repo.py; backend/app/routers/projects.py; backend/tests/test_project_billing.py
- **Decisions made**: billable project = active, on_hold or completed, or cancelled with approved_at set; no approved_at date filter, so the fee goes on the next run created after approval
- **Open questions**: (none)
- **Conventions established**: invoice lines from project billing set project_id; fixed-fee lines and $0 lines are kind 'project', T&M lines are kind 'time'; LineOut does not expose project_id yet

## Requirements Covered
- REQ-08

### Failed verification output
`service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_project_billing.py tests/test_projects.py tests/test_projects_api.py tests/test_invoicing.py tests/test_block_billing.py tests/test_block_agreements.py`
```
OST http://testserver/api/projects "HTTP/1.1 201 Created"
2026-10-21 07:45:36,782 INFO httpx2 HTTP Request: POST http://testserver/api/projects/1/approve "HTTP/1.1 200 OK"
2026-10-21 07:45:36,814 INFO httpx2 HTTP Request: POST http://testserver/api/projects/1/bill-fixed-fee "HTTP/1.1 201 Created"
------------------------------ Captured log call -------------------------------
INFO     httpx2:_client.py:1085 HTTP Request: POST http://testserver/api/projects "HTTP/1.1 201 Created"
INFO     httpx2:_client.py:1085 HTTP Request: POST http://testserver/api/projects/1/approve "HTTP/1.1 200 OK"
INFO     httpx2:_client.py:1085 HTTP Request: POST http://testserver/api/projects/1/bill-fixed-fee "HTTP/1.1 201 Created"
=========================== short test summary info ============================
FAILED tests/test_project_billing.py::test_worked_example_three_runs_bill_exactly_the_budget
FAILED tests/test_project_billing.py::test_budget_lowered_below_billed_puts_new_time_over_budget
FAILED tests/test_project_billing.py::test_fixed_fee_bills_once_on_the_next_run_and_covers_time
FAILED tests/test_project_billing.py::test_untaxed_fee_and_no_time_gives_one_line
FAILED tests/test_project_billing.py::test_bill_fixed_fee_now_makes_a_one_off_draft
FAILED tests/test_project_billing.py::test_voiding_the_fee_invoice_releases_fee_and_time_and_rerun_bills_again
FAILED tests/test_project_billing.py::test_voiding_or_deleting_the_one_off_fee_lets_it_bill_again
7 failed, 137 passed in 101.16s (0:01:41)

```
`service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q -k 'bill or invoice or run or block or proration or credit or payment'`
```
erver/api/projects "HTTP/1.1 201 Created"
2026-10-21 07:50:45,131 INFO httpx2 HTTP Request: POST http://testserver/api/projects/1/approve "HTTP/1.1 200 OK"
2026-10-21 07:50:45,172 INFO httpx2 HTTP Request: POST http://testserver/api/projects/1/bill-fixed-fee "HTTP/1.1 201 Created"
------------------------------ Captured log call -------------------------------
INFO     httpx2:_client.py:1085 HTTP Request: POST http://testserver/api/projects "HTTP/1.1 201 Created"
INFO     httpx2:_client.py:1085 HTTP Request: POST http://testserver/api/projects/1/approve "HTTP/1.1 200 OK"
INFO     httpx2:_client.py:1085 HTTP Request: POST http://testserver/api/projects/1/bill-fixed-fee "HTTP/1.1 201 Created"
=========================== short test summary info ============================
FAILED tests/test_project_billing.py::test_worked_example_three_runs_bill_exactly_the_budget
FAILED tests/test_project_billing.py::test_budget_lowered_below_billed_puts_new_time_over_budget
FAILED tests/test_project_billing.py::test_fixed_fee_bills_once_on_the_next_run_and_covers_time
FAILED tests/test_project_billing.py::test_untaxed_fee_and_no_time_gives_one_line
FAILED tests/test_project_billing.py::test_bill_fixed_fee_now_makes_a_one_off_draft
FAILED tests/test_project_billing.py::test_voiding_the_fee_invoice_releases_fee_and_time_and_rerun_bills_again
FAILED tests/test_project_billing.py::test_voiding_or_deleting_the_one_off_fee_lets_it_bill_again
7 failed, 312 passed, 974 deselected in 259.32s (0:04:19)

```
`service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_project_billing.py`
```
P Request: POST http://testserver/api/projects "HTTP/1.1 201 Created"
2026-10-21 07:52:43,040 INFO httpx2 HTTP Request: POST http://testserver/api/projects/1/approve "HTTP/1.1 200 OK"
2026-10-21 07:52:43,073 INFO httpx2 HTTP Request: POST http://testserver/api/projects/1/bill-fixed-fee "HTTP/1.1 201 Created"
------------------------------ Captured log call -------------------------------
INFO     httpx2:_client.py:1085 HTTP Request: POST http://testserver/api/projects "HTTP/1.1 201 Created"
INFO     httpx2:_client.py:1085 HTTP Request: POST http://testserver/api/projects/1/approve "HTTP/1.1 200 OK"
INFO     httpx2:_client.py:1085 HTTP Request: POST http://testserver/api/projects/1/bill-fixed-fee "HTTP/1.1 201 Created"
=========================== short test summary info ============================
FAILED tests/test_project_billing.py::test_worked_example_three_runs_bill_exactly_the_budget
FAILED tests/test_project_billing.py::test_budget_lowered_below_billed_puts_new_time_over_budget
FAILED tests/test_project_billing.py::test_fixed_fee_bills_once_on_the_next_run_and_covers_time
FAILED tests/test_project_billing.py::test_untaxed_fee_and_no_time_gives_one_line
FAILED tests/test_project_billing.py::test_bill_fixed_fee_now_makes_a_one_off_draft
FAILED tests/test_project_billing.py::test_voiding_the_fee_invoice_releases_fee_and_time_and_rerun_bills_again
FAILED tests/test_project_billing.py::test_voiding_or_deleting_the_one_off_fee_lets_it_bill_again
7 failed, 10 passed in 21.60s

```

## Token Usage
38 requests, 3718862 input tokens (3466447 cached), 38615 output tokens, $2.7276
