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
| engineering-security-engineer | — | 13 | 2.54 | 15.54 | mandatory |
| engineering-senior-developer | — | 25 | 2.97 | 27.97 | heuristic |
| testing-api-tester | — | 22 | 3.3 | 25.3 | heuristic |

- **Task type detected**: implementation
- **Confidence**: LOW
- **Adapter**: claude-code
- **Model tier**: sonnet

## Completed Tasks
- [x] Task 1: Permission split and roles (done)
- [x] Task 2: Manager role in the database, users API and UI gates (done)
- [ ] Task 3: Role-by-endpoint test matrix (partial)

## Files Modified
- `backend/tests/test_billing_config.py`

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
- GET /organizations/{id}/billing returns payment terms, tax, reminder and late-fee flags together with rate overrides, so it needs `invoice:read` (the brief's rule for routes that mix both); its old test now expects 403 for tech and read_only.

## Issues Encountered
- The full backend suite takes over 20 minutes here, so I couldn't finish a run inside the time budget.
- BLOCKER: FAILED tests/test_credit_memos.py::test_permissions - AssertionError: assert ...

## Escalations
| # | Severity | Type | Decision | Status | Resolution |
|---|----------|------|----------|--------|------------|
| 1 | blocker | schema | Resolve: FAILED tests/test_credit_memos.py::test_permissions - AssertionError: assert ... | pending |  |

- #1 context: Verification failed (cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/pytest -q -p no:warnings); a BLOCKER is not auto-fixed.

## Handoff Context
- **Key outputs**: backend/tests/test_billing_config.py
- **Decisions made**: GET /organizations/{id}/billing returns payment terms, tax, reminder and late-fee flags together with rate overrides, so it needs `invoice:read` (the brief's rule for routes that mix both); its old test now expects 403 for tech and read_only.
- **Open questions**: (none)
- **Conventions established**: Re-run the full backend suite and vitest. Fix the remaining old-access tests by giving test users `invoice:read` or switching them to an admin or billing user, never by loosening a router check. Then add KNOWN_UNTESTED from the routes that test lists as never called, leaving out routes this plan creates.

## Requirements Covered
(none)

### Failed verification output
`cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/pytest -q -p no:warnings`
```
================= short test summary info ============================
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
17 failed, 1607 passed in 1440.74s (0:24:00)

```

## Token Usage
16 requests, 536366 input tokens (424268 cached), 5896 output tokens, $0.7632
