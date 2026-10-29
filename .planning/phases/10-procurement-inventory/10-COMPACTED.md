---
phase: 10-procurement-inventory
compacted: 2026-10-29
original_summaries: [10-01-SUMMARY.md, 10-02-SUMMARY.md, 10-03-SUMMARY.md]
requirements_satisfied: [REQ-10]
---

# Phase 10: Procurement & inventory — Compacted Summary

## Deliverables
- 10-01 Procurement schema, models and permissions (Complete): backend/alembic/versions/0031_procurement.py, backend/app/models.py, backend/app/permissions.py, backend/app/procurement_schemas.py, backend/tests/conftest.py, backend/tests/test_permissions.py, backend/tests/test_procurement_schema.py
- 10-02 Procurement service and API: vendors, POs, receiving, inventory, delivery billing, markup (Complete): backend/alembic/versions/0031_procurement.py, backend/app/main.py, backend/app/procurement.py, backend/app/procurement_schemas.py, backend/app/routers/procurement.py, backend/app/schemas.py, backend/tests/test_procurement.py, backend/tests/test_procurement_api.py, backend/tests/test_procurement_schema.py
- 10-03 Procurement UI, client inventory card and docs (Complete with Warnings): docs/BILLING.md, docs/PROCUREMENT.md, docs/verify/procurement.md, frontend/src/App.tsx, frontend/src/Procurement.test.tsx, frontend/src/api.ts, frontend/src/pages/OrgInventoryCard.tsx, frontend/src/pages/OrganizationDetail.tsx, frontend/src/pages/procurement/Inventory.tsx, frontend/src/pages/procurement/MarkupRules.tsx, frontend/src/pages/procurement/PurchaseOrderPage.tsx, frontend/src/pages/procurement/PurchaseOrders.tsx, frontend/src/pages/procurement/Vendors.tsx

## Decisions
- 10-01: `purchase_orders.number` is a nullable `String(20)` with a unique constraint, and the service sets `PO-<id>` after insert, as the plan allowed.
- 10-01: `purchase_order_lines` also gets `created_at` and `updated_at` through `TimestampMixin`; the plan did not list them for lines.
- 10-01: Constraint and index names: `uq_vendors_name`, `uq_inventory_serial`, `ck_po_lines_*`, `ck_inventory_*`, `ck_markup_rules_*`, `uq_markup_rules_product`, `uq_mar
- 10-02: `config_services.py` and `routers/billing.py` are unchanged: settings and product routes already pass the whole body through, so the schema additions were enoug
- 10-02: Vendor archive and restore go through `PATCH /vendors/{id}` with `archived: true|false`, because the route list has no archive route.
- 10-02: `POST /order` takes no body. `ordered_on` is the value already set on the draft (via PATCH), otherwise today in the business timezone.
- 10-03: The plan lists no layout file, so the tabs and `ProcurementNav` live in PurchaseOrders.tsx. Vendors and POs are two tabs switched by component state at /procure
- 10-03: The default markup is read and saved through GET and PATCH /settings (`default_markup_bp`), because there is no procurement route for it.
- 10-03: The taxable flag on a PO line is a select (From product / Yes / No); "From product" sends null.

## Conventions and Open Questions
- 10-01 convention: The service must set `purchase_orders.number = 'PO-<id>'` in the same transaction as the insert.
- 10-01 convention: `ReceiveIn` strips serials and rejects blank or case-insensitive duplicate serials. The database also enforces serial uniqueness through `uq_inventory_serial`.
- 10-01 convention: The new tables have no RLS and `psa_app` has no DELETE on them. Removing a PO line therefore has to go through the ON DELETE CASCADE from the PO, or be avoided.
- 10-02 convention: Service entry points in `app/procurement.py`: `resolve_markup`, `receive`, `deliver`, `undo_delivery`, `consume`, `list_org_inventory`.
- 10-02 convention: Permissions: `procurement:read` for reads, `procurement:write` for writes, `billing:write` for markup-rule changes (techs get 403).
- 10-02 convention: Audit actions: `vendor.*`, `purchase_order.*`, `inventory.deliver`, `inventory.undo_delivery`, `inventory.consume`, `markup_rule.*`, plus `charge.create` and `c
- 10-03 convention: Query keys all start with ["procurement", ...], so one invalidation covers the whole area.
- 10-03 convention: Tests use the `go(path, role, perms, handlers)` pattern from Crm.test.tsx.
- 10-03 convention: The owner checklist in .planning/VERIFY.md asks the owner to confirm four assumed rules: bill on delivery, markup order, default markup 0%, and taxability from 

## Files Modified
| File | Change |
|------|--------|
| `backend/alembic/versions/0031_procurement.py` | 10-01: Procurement schema, models and permissions |
| `backend/app/models.py` | 10-01: Procurement schema, models and permissions |
| `backend/app/permissions.py` | 10-01: Procurement schema, models and permissions |
| `backend/app/procurement_schemas.py` | 10-01: Procurement schema, models and permissions |
| `backend/tests/conftest.py` | 10-01: Procurement schema, models and permissions |
| `backend/tests/test_permissions.py` | 10-01: Procurement schema, models and permissions |
| `backend/tests/test_procurement_schema.py` | 10-01: Procurement schema, models and permissions |
| `backend/alembic/versions/0031_procurement.py` | 10-02: Procurement service and API: vendors, POs, receiving, inventory, delivery billing, markup |
| `backend/app/main.py` | 10-02: Procurement service and API: vendors, POs, receiving, inventory, delivery billing, markup |
| `backend/app/procurement.py` | 10-02: Procurement service and API: vendors, POs, receiving, inventory, delivery billing, markup |
| `backend/app/procurement_schemas.py` | 10-02: Procurement service and API: vendors, POs, receiving, inventory, delivery billing, markup |
| `backend/app/routers/procurement.py` | 10-02: Procurement service and API: vendors, POs, receiving, inventory, delivery billing, markup |
| `backend/app/schemas.py` | 10-02: Procurement service and API: vendors, POs, receiving, inventory, delivery billing, markup |
| `backend/tests/test_procurement.py` | 10-02: Procurement service and API: vendors, POs, receiving, inventory, delivery billing, markup |
| `backend/tests/test_procurement_api.py` | 10-02: Procurement service and API: vendors, POs, receiving, inventory, delivery billing, markup |
| `backend/tests/test_procurement_schema.py` | 10-02: Procurement service and API: vendors, POs, receiving, inventory, delivery billing, markup |
| `docs/BILLING.md` | 10-03: Procurement UI, client inventory card and docs |
| `docs/PROCUREMENT.md` | 10-03: Procurement UI, client inventory card and docs |
| `docs/verify/procurement.md` | 10-03: Procurement UI, client inventory card and docs |
| `frontend/src/App.tsx` | 10-03: Procurement UI, client inventory card and docs |
| `frontend/src/Procurement.test.tsx` | 10-03: Procurement UI, client inventory card and docs |
| `frontend/src/api.ts` | 10-03: Procurement UI, client inventory card and docs |
| `frontend/src/pages/OrgInventoryCard.tsx` | 10-03: Procurement UI, client inventory card and docs |
| `frontend/src/pages/OrganizationDetail.tsx` | 10-03: Procurement UI, client inventory card and docs |
| `frontend/src/pages/procurement/Inventory.tsx` | 10-03: Procurement UI, client inventory card and docs |
| `frontend/src/pages/procurement/MarkupRules.tsx` | 10-03: Procurement UI, client inventory card and docs |
| `frontend/src/pages/procurement/PurchaseOrderPage.tsx` | 10-03: Procurement UI, client inventory card and docs |
| `frontend/src/pages/procurement/PurchaseOrders.tsx` | 10-03: Procurement UI, client inventory card and docs |
| `frontend/src/pages/procurement/Vendors.tsx` | 10-03: Procurement UI, client inventory card and docs |

## Verification
- 10-01 (REQ-10): 6/6 verification commands passed
- 10-02 (REQ-10): 6/6 verification commands passed
- 10-03 (REQ-10): 5/5 verification commands passed

## Agents
- 10-01: engineering-backend-architect
- 10-02: engineering-senior-developer
- 10-03: engineering-frontend-developer

## Also Covered
- backend/tests/test_seed_and_migrations.py
- backend/app/config_services.py
- backend/app/routers/billing.py
