# Phase 10: Procurement & inventory -- Context

## Phase Goal
Hardware and software purchases are ordered from vendors, received (with serial numbers), tracked in inventory to a client and asset, and billed to the client at cost plus markup through the existing billing run.

## Requirements Covered
- REQ-10: Procurement & inventory: vendors and purchase orders with receiving; serialised inventory tracked to client/asset; markup rules feed invoice lines

## What Already Exists (from prior phases)
- products (models.py Product: sku, name, unit_price_cents, cost_cents, taxable, archived_at; migration 0003) and the product catalog API in app/routers/billing.py
- product_charges (models.py ProductCharge): one-off client charges pulled by billing._pull_charges into 'product' invoice lines on the normal billing run; tax = org.tax_rate_bp when taxable; voided_at excludes a charge; invoice_line_id set once invoiced
- app/money.py marked_up(cost_cents, markup_bp) (cost + round-half-up markup) and line_amounts; billable expenses already bill at marked_up cost via _pull_expenses (precedent)
- assets (models.py ~1618, migration 0010, client-scoped with RLS, serial number, warranty; app/routers/assets.py)
- RLS pattern (0030_crm.py ~176): ENABLE + FORCE RLS, policy org_scope USING/WITH CHECK app_org_visible(organization_id), GRANT SELECT, INSERT, UPDATE to the app role; staff-internal tables have no RLS but still get the grants
- permissions.py MATRIX with _READ set; routers registered in main.py; tests/conftest.py TABLES (~34) and RESEED (~44) lists and HIT_ROUTES; tests/test_zz_api_contract.py requires every route to have a summary, a tag, a permission and to be hit by the suite
- Latest migration: 0030_crm (revision '0030')

## Key Design Decisions
- Billing reuses the existing charge path: delivering a billable inventory item to a client creates a ProductCharge priced at marked_up(unit_cost_cents, markup_bp) per unit; billing.py and money.py are NOT changed. (assumed, confirm in Phase 14)
- Items are billed when delivered to the client, not when received. Undoing a delivery voids its charge only while the charge is not yet invoiced; after invoicing, the API refuses and points to a credit memo. (assumed)
- Markup resolution, first match wins: PO line markup_bp, then a product markup rule, then a rule for the product's category (hardware|software|license|other), then settings.default_markup_bp (default 0 = bill at cost). The markup used is frozen on the inventory item at delivery. (assumed; owner sets the real percentages)
- Taxability: the product's taxable flag; a PO line without a product is taxable unless the line says otherwise (same as normal invoices, per PRF-002 'nothing different on tax').
- Procurement tables: vendors, purchase_order_lines and markup_rules are staff-internal (no RLS). purchase_orders and inventory_items carry a nullable organization_id, so they use the standard org_scope RLS policy, as expenses do (staff with scope 'all' also see stock rows with no client; a client scope never does). CORRECTED after the build: the first plan made them staff-internal, which broke the test_isolation invariant that every table with organization_id has forced RLS.
- Serial numbers are globally unique case-insensitively (partial unique index on lower(serial_number)). Serialised lines create one inventory item per serial (quantity 1); non-serialised lines create one item carrying the received quantity.
- Permissions: procurement:read for all staff (_READ); procurement:write for admin, tech and billing; markup rules and default markup need the existing billing:write permission.
- Architecture proposals: skipped (no spec; auto default).

## Plan Structure
- **Plan 10-01 (Wave 1)**: Procurement schema, models and permissions -- Add migration 0031_procurement with vendors, purchase orders and lines, inventory items, markup rules, product category and the default markup setting, plus models, Pydantic schemas, permissions and schema tests.
- **Plan 10-02 (Wave 2)**: Procurement service and API: vendors, POs, receiving, inventory, delivery billing, markup -- Implement app/procurement.py and routers/procurement.py: vendor CRUD, the purchase order lifecycle, receiving with serials, inventory listing, delivery to a client that creates a marked-up product charge (and optionally an asset), undoing a delivery, and markup rules with resolution.
- **Plan 10-03 (Wave 3)**: Procurement UI, client inventory card and docs -- Add the staff UI for vendors, purchase orders (create, order, receive with serials), inventory (deliver, undo, consume) and markup rules, a client inventory card on the organization page, and the procurement docs and verify checklist.
