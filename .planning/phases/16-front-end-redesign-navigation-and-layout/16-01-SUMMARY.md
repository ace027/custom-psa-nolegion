# Plan 16-01 Summary: Permission split and manager role

## Result
**Status**: Partial
**Wave**: 1
**Agent**: engineering-security-engineer
**Completed**: 2026-11-02
**Failure Class**: BLOCKER — FAILED tests/test_credit_memos.py::test_permissions - AssertionError: assert ...

## Agent Selection Rationale

| Candidate | Semantic | Heuristic | Memory | Total | Source |
|-----------|----------|-----------|--------|-------|--------|
| engineering-security-engineer | — | 10 | 2.54 | 12.54 | mandatory |
| testing-api-tester | — | 22 | 3.3 | 25.3 | heuristic |
| engineering-senior-developer | — | 22 | 2.97 | 24.97 | heuristic |

- **Task type detected**: implementation
- **Confidence**: LOW
- **Adapter**: claude-code
- **Model tier**: sonnet

## Completed Tasks
- [x] Task 1: Permission split and roles (done)
- [x] Task 2: Manager role in the database, users API and UI gates (done)
- [ ] Task 3: Role-by-endpoint test matrix (partial)

## Files Modified
- `backend/app/scheduling.py`
- `backend/app/ticket_services.py`
- `backend/tests/test_role_matrix.py`
- `backend/tests/test_scheduling_api.py`
- `backend/tests/test_tickets.py`
- `backend/tests/test_zz_api_contract.py`
- `frontend/src/Billing.test.tsx`
- `frontend/src/Payments.test.tsx`
- `frontend/src/Phase3B.test.tsx`
- `frontend/src/Phase3C.test.tsx`

## Verification Results
7/8 verification commands passed (run by Triad after the agent finished).

## Verification Commands
| Command | Exit Code | Result |
|---------|-----------|--------|
| `cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/ruff check app tests` | 0 | PASS |
| `cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/python -m app.openapi_export --check` | 0 | PASS |
| `cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/pytest -q -p no:warnings` | 1 | FAIL |
| `cd frontend && npm run -s typecheck && npx vitest run` | 0 | PASS |
| `cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/python -c "from app import permissions as P; assert 'manager' in P.ROLES; m=P.MATRIX; assert 'invoice:read' not in m['tech'] and 'procurement:read' not in m['tech'] and 'procurement:read' not in m['read_only']; assert {'invoice:read','service:configure','report:read','audit:read','timesheet:approve'} <= m['manager']; assert 'config:manage' not in m['manager'] and 'billing:finalize' not in m['manager']"` | 0 | PASS |
| `cd backend && grep -q "manager" alembic/versions/0039_manager_role_and_permission_split.py` | 0 | PASS |
| `cd frontend && npm run -s typecheck` | 0 | PASS |
| `cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/pytest -q -p no:warnings tests/test_role_matrix.py tests/test_seed_and_migrations.py tests/test_zz_api_contract.py` | 0 | PASS |

## Key Decisions
- service:configure covers only the areas DECISIONS.md names: queues, categories, priorities (which hold the SLA targets), work types, statuses and holidays. Ticket types, custom fields, canned responses, time and expense categories, CRM stages, report schedules and PATCH /settings stay on config:manage.

## Issues Encountered
- The 18 full-suite failures are: test_billing_config:93; test_billing_permissions_audit [tech]/[read_only]; test_billing_runs:337; test_credit_memos:448; test_late_fees:187; test_notice_permissions_audit [tech]/[read_only]; test_payment_permissions_audit [tech]/[read_only] and test_techs_can_see_balances_but_not_change_them; test_permissions::test_procurement_permissions; test_procurement:96 and :213; test_procurement_api test_every_route_responds and test_permissions; test_scheduling_schema:206 (expects BOOKABLE_ROLES {'admin','tech'}); test_zz_api_contract coverage (about 250 routes never called).
- BLOCKER: FAILED tests/test_credit_memos.py::test_permissions - AssertionError: assert ...

## Escalations
| # | Severity | Type | Decision | Status | Resolution |
|---|----------|------|----------|--------|------------|
| 1 | warning | quality-gate | The full backend suite does not pass (18 failures). One of them comes from the test_zz_api_contract fix the owner approved: the coverage test now really runs and lists about 250 routes no test calls. Writing tests for all of them is a separate piece of work. | approved | Owner: allowlist today's untested routes (KNOWN_UNTESTED, shrink-only) and track paying it down as follow-up work; update old-access tests to the new matrix. |
| 2 | info | api-contract | Ticket types, custom fields, canned responses, time and expense categories, and PATCH /settings (which mixes business hours and SLA settings with mail and billing) stay on config:manage, so managers cannot edit them. | approved | Owner: correct as built. Managers configure only the service settings; the rest stays admin-only. |
| 3 | blocker | schema | Resolve: FAILED tests/test_credit_memos.py::test_permissions - AssertionError: assert ... | approved | Update the failing old-access tests to the new matrix (all of backend/tests/ is writable). |

- #1 context: Triad will see a failing full suite. Either schedule a follow-up to update the old-access tests and investigate the two test_procurement.py failures, or accept the coverage gap as a separate decision.
- #2 context: DECISIONS.md lists only queues, categories, priorities, statuses, work types, SLA and holidays as service settings. The owner should confirm whether managers also need any of these.
- #3 context: Verification failed (cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/pytest -q -p no:warnings); a BLOCKER is not auto-fixed.

## Handoff Context
- **Key outputs**: backend/app/scheduling.py; backend/app/ticket_services.py; backend/tests/test_role_matrix.py; backend/tests/test_scheduling_api.py; backend/tests/test_tickets.py; backend/tests/test_zz_api_contract.py; frontend/src/Billing.test.tsx; frontend/src/Payments.test.tsx; frontend/src/Phase3B.test.tsx; frontend/src/Phase3C.test.tsx
- **Decisions made**: service:configure covers only the areas DECISIONS.md names: queues, categories, priorities (which hold the SLA targets), work types, statuses and holidays. Ticket types, custom fields, canned responses, time and expense categories, CRM stages, report schedules and PATCH /settings stay on config:manage.
- **Open questions**: (none)
- **Conventions established**: Next, update the old-access tests to the new matrix. Never loosen a router permission check to make one pass.

## Requirements Covered
(none)

### Failed verification output
`cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/pytest -q -p no:warnings`
```
billing_config.py::test_only_billing_roles_can_change_billing_settings
FAILED tests/test_billing_permissions_audit.py::test_billing_role_matrix[tech]
FAILED tests/test_billing_permissions_audit.py::test_billing_role_matrix[read_only]
FAILED tests/test_billing_runs.py::test_run_endpoint_errors_and_permissions
FAILED tests/test_credit_memos.py::test_permissions - AssertionError: assert ...
FAILED tests/test_late_fees.py::test_isolation_between_clients_and_permissions
FAILED tests/test_notice_permissions_audit.py::test_notice_role_matrix[tech]
FAILED tests/test_notice_permissions_audit.py::test_notice_role_matrix[read_only]
FAILED tests/test_payment_permissions_audit.py::test_payment_role_matrix[tech]
FAILED tests/test_payment_permissions_audit.py::test_payment_role_matrix[read_only]
FAILED tests/test_payment_permissions_audit.py::test_techs_can_see_balances_but_not_change_them
FAILED tests/test_permissions.py::test_procurement_permissions - AssertionErr...
FAILED tests/test_procurement.py::test_vendor_crud_archive_and_duplicates - T...
FAILED tests/test_procurement.py::test_markup_rule_crud_and_duplicates - Asse...
FAILED tests/test_procurement_api.py::test_every_route_responds - AssertionEr...
FAILED tests/test_procurement_api.py::test_permissions - AssertionError: asse...
FAILED tests/test_scheduling_schema.py::test_scheduling_permissions - Asserti...
FAILED tests/test_zz_api_contract.py::test_every_route_is_exercised_by_the_suite
18 failed, 1606 passed in 1231.87s (0:20:31)

```

## Token Usage
45 requests, 2628029 input tokens (2300347 cached), 20486 output tokens, $2.5081
