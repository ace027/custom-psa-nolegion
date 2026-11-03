# Phase 17: Agreement billing and profitability — Review Fixes

Fixes applied by the review loop, one section per cycle. Re-review decides whether each one holds.

## Cycle 1

**Date**: 2026-11-03
**Checks**: 19/19 passed
**Files changed**: `backend/app/reports.py`, `backend/tests/test_agreement_billing.py`

| Finding | Severity | File | Agent | Status | Notes |
|---------|----------|------|-------|--------|-------|
| F-001 | major | `backend/app/reports.py (not in the review list, but it breaks the "never billed as extra" criterion in the listed files)` | engineering-senior-developer | fix applied | F-001 fixed. `reports.unbilled` now applies `_not_all_inclusive()`, imported from `billing_repo`, so all-inclusive flat time no longer shows in `/reports/unbilled`, its CSV or the dashboard unbilled tile. I added a test for it. |
