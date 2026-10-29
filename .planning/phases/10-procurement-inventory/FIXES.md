# Phase 10: Procurement & inventory — Review Fixes

Fixes applied by the review loop, one section per cycle. Re-review decides whether each one holds.

## Cycle 1

**Date**: 2026-10-29
**Checks**: 16/16 passed
**Files changed**: `backend/app/procurement_schemas.py`, `backend/tests/test_procurement_api.py`, `frontend/src/pages/procurement/Inventory.tsx`, `frontend/src/pages/procurement/PurchaseOrderPage.tsx`, `frontend/src/pages/procurement/PurchaseOrders.tsx`, `frontend/src/pages/procurement/Vendors.tsx`

| Finding | Severity | File | Agent | Status | Notes |
|---------|----------|------|-------|--------|-------|
| F-001 | major | `frontend/src/pages/procurement/Inventory.tsx` | engineering-frontend-developer | fix applied | Fixed F-001, F-002, F-006 and F-007 in the four procurement pages. tsc is clean and the 9 tests in Procurement.test.tsx pass. I added no new tests for the focus and Escape behaviour, and I did not test with a screen reader. |
| F-002 | major | `frontend/src/pages/procurement/Vendors.tsx` | engineering-frontend-developer | fix applied | Fixed F-001, F-002, F-006 and F-007 in the four procurement pages. tsc is clean and the 9 tests in Procurement.test.tsx pass. I added no new tests for the focus and Escape behaviour, and I did not test with a screen reader. |
| F-006 | major | `frontend/src/pages/procurement/PurchaseOrders.tsx` | engineering-frontend-developer | fix applied | Fixed F-001, F-002, F-006 and F-007 in the four procurement pages. tsc is clean and the 9 tests in Procurement.test.tsx pass. I added no new tests for the focus and Escape behaviour, and I did not test with a screen reader. |
| F-007 | major | `frontend/src/pages/procurement/PurchaseOrderPage.tsx` | engineering-frontend-developer | fix applied | Fixed F-001, F-002, F-006 and F-007 in the four procurement pages. tsc is clean and the 9 tests in Procurement.test.tsx pass. I added no new tests for the focus and Escape behaviour, and I did not test with a screen reader. |
| F-005 | major | `backend/app/procurement_schemas.py` | engineering-backend-architect | fix applied | `DeliverIn.quantity` is now `int / None = Field(default=None, gt=0, le=1_000_000)`, so an omitted quantity reaches the service as `None` and delivers the whole row. I added an API test that omits `quantity` on a 5-unit row. It checks the full 5 units are delivered and no stock is left behind. |
