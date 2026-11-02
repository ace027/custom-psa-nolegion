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
| engineering-security-engineer | — | 10 | 2.55 | 12.55 | mandatory |
| engineering-senior-developer | — | 20 | 2.97 | 22.97 | heuristic |
| testing-api-tester | — | 19 | 3.3 | 22.3 | heuristic |

- **Task type detected**: implementation
- **Confidence**: LOW
- **Adapter**: claude-code
- **Model tier**: sonnet

## Completed Tasks
- [x] Task 1: Permission split and roles (done)
- [ ] Task 2: Manager role in the database, users API and UI gates (partial)
- [ ] Task 3: Role-by-endpoint test matrix (failed)

## Files Modified
- `backend/alembic/versions/0039_manager_role_and_permission_split.py`
- `backend/app/permissions.py`
- `backend/app/routers/billing.py`
- `backend/app/routers/config.py`
- `backend/app/routers/credit_memos.py`
- `backend/app/routers/holidays.py`
- `backend/app/routers/invoices.py`
- `backend/app/routers/late_fees.py`
- `backend/app/routers/notices.py`
- `backend/app/routers/payments.py`
- `backend/app/routers/ticket_config.py`
- `backend/app/schemas.py`
- `docs/api/openapi.json`
- `frontend/src/api.ts`
- `frontend/src/pages/OrganizationDetail.tsx`
- `frontend/src/pages/Users.tsx`
- `frontend/src/pages/billing/BillingLayout.tsx`
- `frontend/src/pages/billing/Receivables.tsx`
- `frontend/src/pages/billing/Reminders.tsx`

## Verification Results
5/8 verification commands passed (run by Triad after the agent finished).

## Verification Commands
| Command | Exit Code | Result |
|---------|-----------|--------|
| `cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/ruff check app tests` | 0 | PASS |
| `cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/python -m app.openapi_export --check` | 0 | PASS |
| `cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/pytest -q -p no:warnings` | 1 | FAIL |
| `cd frontend && npm run -s typecheck && npx vitest run` | 1 | FAIL |
| `cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/python -c "from app import permissions as P; assert 'manager' in P.ROLES; m=P.MATRIX; assert 'invoice:read' not in m['tech'] and 'procurement:read' not in m['tech'] and 'procurement:read' not in m['read_only']; assert {'invoice:read','service:configure','report:read','audit:read','timesheet:approve'} <= m['manager']; assert 'config:manage' not in m['manager'] and 'billing:finalize' not in m['manager']"` | 0 | PASS |
| `cd backend && grep -q "manager" alembic/versions/0039_manager_role_and_permission_split.py` | 0 | PASS |
| `cd frontend && npm run -s typecheck` | 0 | PASS |
| `cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/pytest -q -p no:warnings tests/test_role_matrix.py tests/test_seed_and_migrations.py tests/test_zz_api_contract.py` | 4 | FAIL |

## Key Decisions
- Re-gated routes, method path old -> new: GET /invoices, /invoices/{id}, /invoices/{id}/pdf, /billing-runs, /billing-runs/{id}, /payments, /payments/{id}, /receivables, /credit-memos, /credit-memos/{id}, /late-fees preview and applied, /billing/reminder-stages, statements list/get/pdf, /billing-notices, /billing-notices/{id}, /organizations/{id}/billing: billing:read -> invoice:read

## Issues Encountered
- Started the local postgresql service, which was down, so the backend tests could run
- BLOCKER: FAILED tests/test_credit_memos.py::test_permissions - AssertionError: assert ...

## Escalations
| # | Severity | Type | Decision | Status | Resolution |
|---|----------|------|----------|--------|------------|
| 1 | warning; type: out-of-scope files; decision: allow editing frontend/src/billing.test.tsx, payments.test.tsx, reminders.test.tsx and the other 2 failing test files to add "invoice:read"/"procurement:read" to their test users; context: these tests pin the old access where billing:read showed invoices, and they are not in files_modified, so the frontend suite cannot go green within this plan's scope. | (missing) | (missing) | pending | INVALID: missing type; missing decision; missing context; severity "warning; type: out-of-scope files; decision: allow editing frontend/src/billing.test.tsx, payments.test.tsx, reminders.test.tsx and the other 2 failing test files to add "invoice:read"/"procurement:read" to their test users; context: these tests pin the old access where billing:read showed invoices, and they are not in files_modified, so the frontend suite cannot go green within this plan's scope." is not one of info, warning, blocker |
| 2 | info; type: requirement; decision: should 'manager' join assignable_roles (app/ticket_services.py) and bookable_roles (app/scheduling.py)?; context: decisions.md says a manager has everything a tech has, but both files are outside this plan's list. | (missing) | (missing) | pending | INVALID: missing type; missing decision; missing context; severity "info; type: requirement; decision: should 'manager' join assignable_roles (app/ticket_services.py) and bookable_roles (app/scheduling.py)?; context: decisions.md says a manager has everything a tech has, but both files are outside this plan's list." is not one of info, warning, blocker |
| 3 | blocker | schema | Resolve: FAILED tests/test_credit_memos.py::test_permissions - AssertionError: assert ... | pending |  |

- #3 context: Verification failed (cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/pytest -q -p no:warnings; cd frontend && npm run -s typecheck && npx vitest run; cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/pytest -q -p no:warnings tests/test_role_matrix.py tests/test_seed_and_migrations.py tests/test_zz_api_contract.py); a BLOCKER is not auto-fixed.

## Handoff Context
- **Key outputs**: backend/alembic/versions/0039_manager_role_and_permission_split.py; backend/app/permissions.py; backend/app/routers/billing.py; backend/app/routers/config.py; backend/app/routers/credit_memos.py; backend/app/routers/holidays.py; backend/app/routers/invoices.py; backend/app/routers/late_fees.py; backend/app/routers/notices.py; backend/app/routers/payments.py; backend/app/routers/ticket_config.py; backend/app/schemas.py; docs/api/openapi.json; frontend/src/api.ts; frontend/src/pages/OrganizationDetail.tsx; frontend/src/pages/Users.tsx; frontend/src/pages/billing/BillingLayout.tsx; frontend/src/pages/billing/Receivables.tsx; frontend/src/pages/billing/Reminders.tsx
- **Decisions made**: Re-gated routes, method path old -> new: GET /invoices, /invoices/{id}, /invoices/{id}/pdf, /billing-runs, /billing-runs/{id}, /payments, /payments/{id}, /receivables, /credit-memos, /credit-memos/{id}, /late-fees preview and applied, /billing/reminder-stages, statements list/get/pdf, /billing-notices, /billing-notices/{id}, /organizations/{id}/billing: billing:read -> invoice:read
- **Open questions**: (none)
- **Conventions established**: Manager cannot open the Settings page yet, because App.tsx (forbidden here) gates it on config:manage. The next navigation wave should expose the service-settings pages on service:configure

## Requirements Covered
(none)

### Failed verification output
`cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/pytest -q -p no:warnings`
```
.py::test_only_billing_roles_can_change_billing_settings
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
FAILED tests/test_seed_and_migrations.py::test_migration_0032_reporting_tables_and_constraints
18 failed, 1601 passed in 1249.93s (0:20:49)

```
`cd frontend && npm run -s typecheck && npx vitest run`
```
px-3 py-1.5 text-sm font-medium disabled:opacity-50 bg-blue-600 text-on-accent hover:bg-blue-700 "[39m
                    [33mtype[39m=[32m"submit"[39m
                  [36m>[39m
                    [0mCreate agreement[0m
                  [36m</button>[39m
                [36m</div>[39m
              [36m</form>[39m
            [36m</div>[39m
          [36m</div>[39m
        [36m</div>[39m
      [36m</main>[39m
    [36m</div>[39m
  [36m</div>[39m
[36m</body>[39m
 ❯ waitForWrapper node_modules/@testing-library/dom/dist/wait-for.js:163:27
 ❯ node_modules/@testing-library/dom/dist/query-helpers.js:86:33
 ❯ src/Reminders.test.tsx:94:25
     92|       [PENDING]: json(page([notice({ kind: "invoice", stage_name: null…
     93|     });
     94|     expect(await screen.findByText("Invoice")).toBeInTheDocument();
       |                         ^
     95|     expect(screen.getByDisplayValue("Invoice INV-2026-0001 from Acme M…
     96|   });

⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯[26/26]⎯


 Test Files  5 failed | 36 passed (41)
      Tests  26 failed | 313 passed (339)
   Start at  09:46:30
   Duration  58.99s (tests 35%, import 33%, environment 27%, setup 4%, transform 1%)

Environment  jsdom was created 41 times · 45.42s total, 27% of tracked time
             create it once per worker with pool: 'vmThreads' (keeps per-file isolation) or isolate: false (shares it across files)
             learn more: https://vitest.dev/guide/improving-performance#test-environments


```
`cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/pytest -q -p no:warnings tests/test_role_matrix.py tests/test_seed_and_migrations.py tests/test_zz_api_contract.py`
```

no tests ran in 0.00s
/tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/lib/python3.12/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
  from starlette.testclient import TestClient as TestClient  # noqa
/tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/lib/python3.12/site-packages/authlib/integrations/httpx_client/assertion_client.py:5: AuthlibDeprecationWarning: The httpx module is deprecated; please use httpx2 instead.
  from ._compat import httpx2
ERROR: file or directory not found: tests/test_role_matrix.py


```

## Token Usage
36 requests, 2052473 input tokens (1852737 cached), 18330 output tokens, $1.7358
