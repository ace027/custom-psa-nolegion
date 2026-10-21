# Phase 8: Projects & project billing — Review Fixes

Fixes applied by the review loop, one section per cycle. Re-review decides whether each one holds.

## Cycle 1

**Date**: 2026-10-21
**Checks**: 19/19 passed
**Files changed**: `frontend/src/api.ts`, `frontend/src/pages/ProjectDetail.tsx`

| Finding | Severity | File | Agent | Status | Notes |
|---------|----------|------|-------|--------|-------|
| F-001 | major | `frontend/src/pages/ProjectDetail.tsx` | engineering-frontend-developer | fix applied | F-001 and F-002 are fixed in ProjectDetail.tsx. The tabs now follow the ARIA tabs pattern. Cancel project and Delete phase ask for confirmation, and the phase buttons carry the phase name in their accessible name. |
| F-002 | major | `frontend/src/pages/ProjectDetail.tsx` | engineering-frontend-developer | fix applied | F-001 and F-002 are fixed in ProjectDetail.tsx. The tabs now follow the ARIA tabs pattern. Cancel project and Delete phase ask for confirmation, and the phase buttons carry the phase name in their accessible name. |
| F-003 | major | `frontend/src/api.ts` | engineering-backend-architect | not fixed | partial |
| F-004 | major | `frontend/src/api.ts` | engineering-backend-architect | not fixed | partial |

## Cycle 2

**Date**: 2026-10-21
**Checks**: 19/19 passed
**Files changed**: `frontend/src/Reports.test.tsx`, `frontend/src/pages/billing/Reports.tsx`

| Finding | Severity | File | Agent | Status | Notes |
|---------|----------|------|-------|--------|-------|
| F-005 | major | `frontend/src/pages/billing/Reports.tsx (consequence of /home/user/custom-psa-nolegion/frontend/src/api.ts:647)` | engineering-frontend-developer | fix applied | Added a "Projects" column to the Revenue table in Reports.tsx, in the header, client rows and totals footer. I also widened the empty-state colSpan from 8 to 9. The test fixture now has project_cents, and the test asserts the header and the $2,500.00 cell. The "By month" section is a bar list of totals, not a table, so it needed no column. |
| F-006 | major | `frontend/src/pages/billing/Reports.tsx (consumer of frontend/src/api.ts RevenueRow)` | engineering-frontend-developer | fix applied | Added a "Projects" column to the Revenue table in Reports.tsx, in the header, client rows and totals footer. I also widened the empty-state colSpan from 8 to 9. The test fixture now has project_cents, and the test asserts the header and the $2,500.00 cell. The "By month" section is a bar list of totals, not a table, so it needed no column. |
| F-007 | major | `frontend/src/api.ts (consumer: frontend/src/pages/billing/Reports.tsx)` | engineering-frontend-developer | fix applied | Added a "Projects" column to the Revenue table in Reports.tsx, in the header, client rows and totals footer. I also widened the empty-state colSpan from 8 to 9. The test fixture now has project_cents, and the test asserts the header and the $2,500.00 cell. The "By month" section is a bar list of totals, not a table, so it needed no column. |
| F-008 | major | `frontend/src/pages/billing/Reports.tsx` | engineering-frontend-developer | fix applied | Added a "Projects" column to the Revenue table in Reports.tsx, in the header, client rows and totals footer. I also widened the empty-state colSpan from 8 to 9. The test fixture now has project_cents, and the test asserts the header and the $2,500.00 cell. The "By month" section is a bar list of totals, not a table, so it needed no column. |
