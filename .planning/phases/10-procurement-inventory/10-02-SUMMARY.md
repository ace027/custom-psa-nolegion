# Plan 10-02 Summary: Procurement service and API: vendors, POs, receiving, inventory, delivery billing, markup

## Result
**Status**: Complete
**Wave**: 2
**Agent**: engineering-senior-developer
**Completed**: 2026-10-29

## Agent Selection Rationale

| Candidate | Semantic | Heuristic | Memory | Total | Source |
|-----------|----------|-----------|--------|-------|--------|
| engineering-senior-developer | — | 19 | 2.6 | 21.6 | heuristic |
| engineering-backend-architect | — | 15 | 2.67 | 17.67 | heuristic |
| testing-qa-verification-specialist | — | 12 | 2.87 | 14.870000000000001 | heuristic |

- **Task type detected**: implementation
- **Confidence**: HIGH
- **Adapter**: claude-code
- **Model tier**: sonnet

## Completed Tasks
- [x] Task 1: Vendors, purchase orders and markup rules (done)
- [x] Task 2: Receiving, inventory and delivery billing (done)
- [x] Task 3: Router, registration and API tests (done)

## Files Modified
- `backend/alembic/versions/0031_procurement.py`
- `backend/app/main.py`
- `backend/app/procurement.py`
- `backend/app/procurement_schemas.py`
- `backend/app/routers/procurement.py`
- `backend/app/schemas.py`
- `backend/tests/test_procurement.py`
- `backend/tests/test_procurement_api.py`
- `backend/tests/test_procurement_schema.py`

## Verification Results
6/6 verification commands passed (run by Triad after the agent finished).

## Verification Commands
| Command | Exit Code | Result |
|---------|-----------|--------|
| `service postgresql start >/dev/null 2>&1; cd backend && ruff check app tests && ruff format --check app tests` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_procurement.py tests/test_procurement_api.py tests/test_procurement_schema.py tests/test_invoicing.py tests/test_expenses.py tests/test_billing_runs.py tests/test_assets_api.py` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_zz_api_contract.py tests/test_permissions.py` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_procurement.py -k 'vendor or order or markup or cancel'` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_procurement.py` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_procurement_api.py tests/test_procurement.py tests/test_zz_api_contract.py` | 0 | PASS |

## Key Decisions
- `config_services.py` and `routers/billing.py` are unchanged: settings and product routes already pass the whole body through, so the schema additions were enough.
- Vendor archive and restore go through `PATCH /vendors/{id}` with `archived: true|false`, because the route list has no archive route.
- `POST /order` takes no body. `ordered_on` is the value already set on the draft (via PATCH), otherwise today in the business timezone.
- `PATCH /purchase-orders/{id}` with `lines` replaces all lines, draft only. Vendor and client changes are also draft only. Notes and dates can change until the PO is received or cancelled.
- Line add and edit return the full PO. Line delete and markup-rule delete return 204. Receive returns 201 with the created items.
- An unknown organization on delivery returns 404; an archived client returns 409.
- Undoing a delivery that was split does not merge the rows back; the delivered row returns to stock as its own item.
- `create_asset` makes an asset of kind `other`, with the item description as the name and the serial plus normalised serial.

## Issues Encountered
- `DeliverIn.quantity` defaults to 1 (from 10-01), so an API delivery of a multi-unit row without `quantity` delivers 1 unit. The service itself treats a missing quantity as the whole row.
- `GET /organizations/{org_id}/inventory` returns in-stock items reserved for the client plus delivered items, and excludes consumed ones.

## Escalations
(none)

## Handoff Context
- **Key outputs**: backend/alembic/versions/0031_procurement.py; backend/app/main.py; backend/app/procurement.py; backend/app/procurement_schemas.py; backend/app/routers/procurement.py; backend/app/schemas.py; backend/tests/test_procurement.py; backend/tests/test_procurement_api.py; backend/tests/test_procurement_schema.py
- **Decisions made**: `config_services.py` and `routers/billing.py` are unchanged: settings and product routes already pass the whole body through, so the schema additions were enough.; Vendor archive and restore go through `PATCH /vendors/{id}` with `archived: true|false`, because the route list has no archive route.; `POST /order` takes no body. `ordered_on` is the value already set on the draft (via PATCH), otherwise today in the business timezone.; `PATCH /purchase-orders/{id}` with `lines` replaces all lines, draft only. Vendor and client changes are also draft only. Notes and dates can change until the PO is received or cancelled.; Line add and edit return the full PO. Line delete and markup-rule delete return 204. Receive returns 201 with the created items.; An unknown organization on delivery returns 404; an archived client returns 409.; Undoing a delivery that was split does not merge the rows back; the delivered row returns to stock as its own item.; `create_asset` makes an asset of kind `other`, with the item description as the name and the serial plus normalised serial.
- **Open questions**: (none)
- **Conventions established**: Service entry points in `app/procurement.py`: `resolve_markup`, `receive`, `deliver`, `undo_delivery`, `consume`, `list_org_inventory`.; Permissions: `procurement:read` for reads, `procurement:write` for writes, `billing:write` for markup-rule changes (techs get 403).; Audit actions: `vendor.*`, `purchase_order.*`, `inventory.deliver`, `inventory.undo_delivery`, `inventory.consume`, `markup_rule.*`, plus `charge.create` and `charge.void` for the delivery charge.; `InventoryItemOut.organization_name` and `PurchaseOrderOut.vendor_name` are filled in the router.; A delivery charge stores the markup in `item.markup_bp` and the charge id in `item.product_charge_id`. Both are cleared on undo.

## Requirements Covered
- REQ-10

## Token Usage
30 requests, 2108703 input tokens (1995977 cached), 46973 output tokens, $1.1507
