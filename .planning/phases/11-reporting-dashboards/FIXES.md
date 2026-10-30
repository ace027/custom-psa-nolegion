# Phase 11: Reporting & dashboards — Review Fixes

Fixes applied by the review loop, one section per cycle. Re-review decides whether each one holds.

## Cycle 1

**Date**: 2026-10-30
**Checks**: 16/16 passed
**Files changed**: `frontend/src/Dashboards.test.tsx`, `frontend/src/pages/Users.tsx`, `frontend/src/pages/reports/SlaReport.tsx`

| Finding | Severity | File | Agent | Status | Notes |
|---------|----------|------|-------|--------|-------|
| F-002 | major | `frontend/src/pages/reports/SlaReport.tsx` | engineering-frontend-developer | fix applied | F-002 and F-003 are fixed. The ReportTable scroll wrapper is now a focusable named region with a focus ring. The Users page controls now have accessible names, and the Edit button is renamed to "Cost rate". |
| F-003 | major | `frontend/src/pages/Users.tsx` | engineering-frontend-developer | fix applied | F-002 and F-003 are fixed. The ReportTable scroll wrapper is now a focusable named region with a focus ring. The Users page controls now have accessible names, and the Edit button is renamed to "Cost rate". |
