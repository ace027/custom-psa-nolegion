# Phase 9: CRM & renewals — Review Fixes

Fixes applied by the review loop, one section per cycle. Re-review decides whether each one holds.

## Cycle 1

**Date**: 2026-10-21
**Checks**: 12/14 passed
**Files changed**: `backend/app/renewals.py`, `backend/tests/test_renewals.py`, `frontend/src/pages/crm/Pipeline.tsx`, `frontend/src/pages/quotes/QuotePage.tsx`

| Finding | Severity | File | Agent | Status | Notes |
|---------|----------|------|-------|--------|-------|
| F-001 | major | `backend/app/renewals.py (called from /home/user/custom-psa-nolegion/backend/app/worker.py 47-59)` | engineering-senior-developer | not fixed | partial |
| F-002 | critical | `backend/app/renewals.py` | engineering-backend-architect | not fixed | partial |
| F-008 | major | `backend/tests/test_renewals.py` | engineering-backend-architect | not fixed | partial |
| F-010 | major | `backend/app/renewals.py` | engineering-backend-architect | not fixed | partial |
| F-007 | major | `frontend/src/pages/crm/Pipeline.tsx` | engineering-frontend-developer | fix applied | F-007 and F-009 are fixed. The board now includes any deactivated stage that still holds deals, and Apply on the quote page now shows why it did nothing. - Pipeline: inactive stages with deals get a column headed "(inactive)". A deal's move select offers the active stages plus its own current stage. - QuotePage: an unparseable price shows an inline `role="alert"` message, which clears when you edit the price. Apply stays disabled until both price and reason are filled in. The reason input has `required` and `aria-required`. - I did not add tests for either change. The existing suite still passes. - Not fixed: the "No opportunities yet" message at line 67. It only checks `all.length`, and orphaned deals now show in columns, so it is no longer wrong. |
| F-009 | major | `frontend/src/pages/quotes/QuotePage.tsx` | engineering-frontend-developer | fix applied | F-007 and F-009 are fixed. The board now includes any deactivated stage that still holds deals, and Apply on the quote page now shows why it did nothing. - Pipeline: inactive stages with deals get a column headed "(inactive)". A deal's move select offers the active stages plus its own current stage. - QuotePage: an unparseable price shows an inline `role="alert"` message, which clears when you edit the price. Apply stays disabled until both price and reason are filled in. The reason input has `required` and `aria-required`. - I did not add tests for either change. The existing suite still passes. - Not fixed: the "No opportunities yet" message at line 67. It only checks `all.length`, and orphaned deals now show in columns, so it is no longer wrong. |
