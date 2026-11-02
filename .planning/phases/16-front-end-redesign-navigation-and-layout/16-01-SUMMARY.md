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
- [x] Task 2: Manager role in the database, users API and UI gates (done)
- [ ] Task 3: Role-by-endpoint test matrix (partial)

## Files Modified
- `backend/tests/test_role_matrix.py`
- `backend/tests/test_seed_and_migrations.py`

## Verification Results
6/8 verification commands passed (run by Triad after the agent finished).

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
| `cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/pytest -q -p no:warnings tests/test_role_matrix.py tests/test_seed_and_migrations.py tests/test_zz_api_contract.py` | 0 | PASS |

## Key Decisions
- `GET /organizations/{id}/billing` (rate overrides plus payment terms, tax and reminder/late-fee flags) mixes catalog and invoice data, so it needs invoice:read. As a result the client page's OrgBillingCard is hidden from tech and read-only users.
- Every lookup created through config.py now needs service:configure for writes: queues, categories, priorities, work types, ticket types, canned responses, time categories and expense categories. Ticket statuses and custom fields also need it. CRM stages, report schedules, `PATCH /settings` and `GET /mail/status` stay config:manage.
- Product charges, products, work-type rates, agreements and markup-rule reads keep their existing permissions.
- An API key is still limited to its owner's role (`api_keys.effective_permission`, unchanged). A test confirms that a key whose owner is a tech gets 403 on /invoices even with invoice:read in its list.

## Issues Encountered
- Old tests outside my file list assert the old access (at least `backend/tests/test_billing_config.py`), plus the 5 frontend test files above. Each needs invoice:read added to its test users, or its asserted status changed for tech/read_only.
- `test_zz_api_contract.py` checks nothing on this FastAPI version (0.162): `app.routes` now holds wrapper objects instead of the actual route entries, so "every route declares a permission" and "every route is exercised" find no routes. This was already the case before this plan, and it hides missing permission checks. `test_role_matrix._routes()` shows the fix (expand `effective_route_contexts()`), but switching the contract test over may surface routes no test calls.
- Two pytest runs against the shared psa_test database at the same time deadlock, so run the suites one after another.
- BLOCKER: FAILED tests/test_credit_memos.py::test_permissions - AssertionError: assert ...

## Escalations
| # | Severity | Type | Decision | Status | Resolution |
|---|----------|------|----------|--------|------------|
| 1 | blocker | out-of-scope-files | Allow updates to existing tests that assume the old access: backend/tests/test_billing_config.py (and any others the full backend run turns up), plus frontend/src/Billing.test.tsx, Payments.test.tsx, Phase3B.test.tsx, Phase3C.test.tsx and Reminders.test.tsx (add "invoice:read" next to "billing:read" in their test users; tried on copies, 27/27 pass). | approved | Owner approved updating tests that pin the old access; backend/tests/ and the named frontend tests added to files_modified. |
| 2 | warning | quality-gate | Fix tests/test_zz_api_contract.api_routes to expand the wrapped routes FastAPI 0.162 puts in app.routes (as test_role_matrix._routes does), so the permission and coverage checks actually run. | approved | Fix api_routes to expand wrapped routes so the contract checks run; file already in scope. |
| 3 | info | architecture | Should managers be assignable to tickets and bookable for appointments (`ticket_services.ASSIGNABLE_ROLES`, `scheduling.BOOKABLE_ROLES`)? | approved | Owner: yes, managers are assignable and bookable like techs; ticket_services.py and scheduling.py added to files_modified. |
| 4 | blocker | schema | Resolve: FAILED tests/test_credit_memos.py::test_permissions - AssertionError: assert ... | approved | Covered by #1: test_credit_memos.py is now writable to match the new access matrix. |

- #1 context: These tests encode the old access rules. The plan requires the full suites to pass but does not list these files as writable.
- #2 context: The contract tests currently pass while checking no routes. This was already the case before this plan, so CI would not catch a new route without a permission check.
- #3 context: The decisions give managers dispatch work; both lists are currently admin and tech only.
- #4 context: Verification failed (cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/pytest -q -p no:warnings; cd frontend && npm run -s typecheck && npx vitest run); a BLOCKER is not auto-fixed.

## Handoff Context
- **Key outputs**: backend/tests/test_role_matrix.py; backend/tests/test_seed_and_migrations.py
- **Decisions made**: `GET /organizations/{id}/billing` (rate overrides plus payment terms, tax and reminder/late-fee flags) mixes catalog and invoice data, so it needs invoice:read. As a result the client page's OrgBillingCard is hidden from tech and read-only users.; Every lookup created through config.py now needs service:configure for writes: queues, categories, priorities, work types, ticket types, canned responses, time categories and expense categories. Ticket statuses and custom fields also need it. CRM stages, report schedules, `PATCH /settings` and `GET /mail/status` stay config:manage.; Product charges, products, work-type rates, agreements and markup-rule reads keep their existing permissions.; An API key is still limited to its owner's role (`api_keys.effective_permission`, unchanged). A test confirms that a key whose owner is a tech gets 403 on /invoices even with invoice:read in its list.
- **Open questions**: (none)
- **Conventions established**: Gate invoice screens on invoice:read and catalog screens on billing:read. Service settings use service:configure; general settings keep config:manage.; App.tsx still shows Billing in the navigation for billing:read. Users without invoice:read are redirected to Agreements, and Phase 16 navigation decides what to show them.; Managers are not assignable or bookable yet (`ticket_services.ASSIGNABLE_ROLES` and `scheduling.BOOKABLE_ROLES` are still admin and tech only), so "dispatch" for managers needs work outside this plan.

## Requirements Covered
(none)

### Failed verification output
`cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/pytest -q -p no:warnings`
```
========= short test summary info ============================
FAILED tests/test_billing_config.py::test_only_billing_roles_can_change_billing_settings
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
17 failed, 1607 passed in 1412.75s (0:23:32)

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
   Start at  10:43:13
   Duration  65.88s (environment 32%, import 31%, tests 30%, setup 5%, transform 1%)

Environment  jsdom was created 41 times · 60.82s total, 32% of tracked time
             create it once per worker with pool: 'vmThreads' (keeps per-file isolation) or isolate: false (shares it across files)
             learn more: https://vitest.dev/guide/improving-performance#test-environments


```

## Token Usage
48 requests, 3021904 input tokens (2769477 cached), 25072 output tokens, $2.3174
