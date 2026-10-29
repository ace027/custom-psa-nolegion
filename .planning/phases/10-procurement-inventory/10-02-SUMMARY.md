# Plan 10-02 Summary: Procurement service and API: vendors, POs, receiving, inventory, delivery billing, markup

## Result
**Status**: BLOCKED
**Wave**: 2
**Agent**: engineering-senior-developer
**Completed**: 2026-10-29
**Failure Class**: BLOCKER — $ service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_procurement.py tests/test_procurement_api.py tests/test_procurement_schema.py tests/test_invoicing.py tests/tes

## Agent Selection Rationale

| Candidate | Semantic | Heuristic | Memory | Total | Source |
|-----------|----------|-----------|--------|-------|--------|
| engineering-senior-developer | — | 19 | 2.59 | 21.59 | heuristic |
| engineering-backend-architect | — | 14 | 2.61 | 16.61 | heuristic |
| testing-qa-verification-specialist | — | 12 | 2.87 | 14.870000000000001 | heuristic |

- **Task type detected**: implementation
- **Confidence**: HIGH
- **Adapter**: claude-code
- **Model tier**: sonnet

## Completed Tasks
- [ ] Task 1: Vendors, purchase orders and markup rules (skipped)
- [ ] Task 2: Receiving, inventory and delivery billing (skipped)
- [ ] Task 3: Router, registration and API tests (skipped)

## Files Modified
(none)

## Verification Results
2/6 verification commands passed (run by Triad after the agent finished).

## Verification Commands
| Command | Exit Code | Result |
|---------|-----------|--------|
| `service postgresql start >/dev/null 2>&1; cd backend && ruff check app tests && ruff format --check app tests` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_procurement.py tests/test_procurement_api.py tests/test_procurement_schema.py tests/test_invoicing.py tests/test_expenses.py tests/test_billing_runs.py tests/test_assets_api.py` | 4 | FAIL |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_zz_api_contract.py tests/test_permissions.py` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_procurement.py -k 'vendor or order or markup or cancel'` | 4 | FAIL |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_procurement.py` | 4 | FAIL |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_procurement_api.py tests/test_procurement.py tests/test_zz_api_contract.py` | 4 | FAIL |

## Key Decisions
(none)

## Issues Encountered
- A PO line cannot be removed through the app role. The PO-level ON DELETE CASCADE does not help, because the PO row cannot be deleted either.
- A markup rule cannot be removed through the app role.
- PurchaseOrderLineIn in procurement_schemas.py requires description, unit_cost_cents and taxable. The plan says the service fills these from the product when the request omits them, so I would make them optional (the file is in my write list). I would also add a PurchaseOrderLinePatch schema.
- config_services.update_settings already applies any key generically under CONFIG_MANAGE. Only SettingsOut and SettingsPatch in schemas.py need default_markup_bp, so config_services.py needs no edit.
- Blocked: The plan requires DELETE routes for PO lines and markup rules, but psa_app has no DELETE grant on those tables (alembic/versions/0031_procurement.py line 171). The fix needs a migration, or a change to the plan.
- BLOCKER: $ service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_procurement.py tests/test_procurement_api.py tests/test_procurement_schema.py tests/test_invoicing.py tests/tes

## Escalations
| # | Severity | Type | Decision | Status | Resolution |
|---|----------|------|----------|--------|------------|
| 1 | blocker | schema | Choose one of these. (a) Add migration 0032 that runs `GRANT DELETE ON purchase_order_lines, markup_rules TO psa_app`. Update the privilege test in test_procurement_schema.py to match. Allow backend/alembic/ and that test file for this plan. (b) Keep the grants as they are and change the routes. For markup rules, DELETE becomes PATCH-only, or the rule gets an archived flag (needs a column, so a migration anyway). For PO lines, a draft line is edited to a zero quantity, or the draft PO is cancelled and recreated. (c) Drop the two DELETE routes from the plan. I recommend (a). Draft-line removal and markup-rule removal are ordinary operations, and neither table holds history that needs protecting. The PO status and the audit log cover the audit need. | approved | Auto run: took the recommended option (a). Unshipped migration 0031 is amended to GRANT DELETE on purchase_order_lines and markup_rules only, matching the 0003 precedent of DELETE on invoice_lines and rates; the privilege test is updated to match. Plan 10-02 is re-planned to allow those two files. |
| 2 | blocker | schema | Resolve: $ service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_procurement.py tests/test_procurement_api.py tests/test_procurement_schema.py tests/test_invoicing.py tests/tes | approved | This was the verification failure caused by #1. It is resolved by the same re-plan, and the rebuild reruns the checks. |

- #1 context: Plan 10-02, interfaces list "PATCH/DELETE /purchase-orders/{id}/lines/{line_id} (draft only)" and "PATCH/DELETE /markup-rules/{id}". The Plan 10-01 handoff already flagged that line removal needs ON DELETE CASCADE or must be avoided. The cascade only fires if the PO is deleted, which is also not granted. Once you decide, I can implement all three tasks in one pass. Everything else in the plan is unambiguous.
- #2 context: Verification failed (service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_procurement.py tests/test_procurement_api.py tests/test_procurement_schema.py tests/test_invoicing.py tests/test_expenses.py tests/test_billing_runs.py tests/test_assets_api.py; service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_procurement.py -k 'vendor or order or markup or cancel'; service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_procurement.py; service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_procurement_api.py tests/test_procurement.py tests/test_zz_api_contract.py); a BLOCKER is not auto-fixed.

## Handoff Context
- **Key outputs**: (none)
- **Decisions made**: (none)
- **Open questions**: (none)
- **Conventions established**: (none)

## Requirements Covered
- REQ-10

### Failed verification output
`service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_procurement.py tests/test_procurement_api.py tests/test_procurement_schema.py tests/test_invoicing.py tests/test_expenses.py tests/test_billing_runs.py tests/test_assets_api.py`
```

no tests ran in 0.00s
ERROR: file or directory not found: tests/test_procurement.py


```
`service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_procurement.py -k 'vendor or order or markup or cancel'`
```

no tests ran in 0.00s
ERROR: file or directory not found: tests/test_procurement.py


```
`service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_procurement.py`
```

no tests ran in 0.00s
ERROR: file or directory not found: tests/test_procurement.py


```
`service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_procurement_api.py tests/test_procurement.py tests/test_zz_api_contract.py`
```

no tests ran in 0.00s
ERROR: file or directory not found: tests/test_procurement_api.py


```

## Token Usage
13 requests, 622150 input tokens (561069 cached), 5865 output tokens, $0.3236
