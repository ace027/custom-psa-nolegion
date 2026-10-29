# Phase 11: Reporting & dashboards — Review Fixes

Fixes applied by the review loop, one section per cycle. Re-review decides whether each one holds.

## Cycle 1

**Date**: 2026-10-29
**Checks**: 16/16 passed
**Files changed**: `frontend/src/pages/Dashboard.tsx`, `frontend/src/pages/reports/AgingReport.tsx`, `frontend/src/pages/reports/ProfitabilityReport.tsx`, `frontend/src/pages/reports/ReportSchedules.tsx`, `frontend/src/pages/reports/SlaReport.tsx`, `frontend/src/pages/reports/UtilisationReport.tsx`

| Finding | Severity | File | Agent | Status | Notes |
|---------|----------|------|-------|--------|-------|
| F-001 | major | `frontend/src/pages/reports/SlaReport.tsx` | engineering-frontend-developer | not fixed | partial |
| F-002 | major | `frontend/src/pages/reports/ReportSchedules.tsx` | engineering-frontend-developer | not fixed | partial |
| F-003 | major | `frontend/src/pages/reports/ReportSchedules.tsx` | engineering-frontend-developer | not fixed | partial |
| F-004 | major | `frontend/src/pages/reports/SlaReport.tsx` | engineering-frontend-developer | not fixed | partial |
| F-005 | major | `frontend/src/pages/reports/SlaReport.tsx (same pattern in AgingReport.tsx, ProfitabilityReport.tsx and UtilisationReport.tsx)` | engineering-frontend-developer | not fixed | partial |
| F-006 | major | `frontend/src/pages/reports/SlaReport.tsx (also Aging, Profitability, Utilisation, Dashboard.tsx Business and MyWeek)` | engineering-frontend-developer | not fixed | partial |
| F-007 | major | `frontend/src/pages/reports/SlaReport.tsx (also Utilisation and Aging tables)` | engineering-frontend-developer | not fixed | partial |

## Cycle 2

**Date**: 2026-10-29
**Checks**: 16/16 passed
**Files changed**: `frontend/src/pages/reports/ReportSchedules.tsx`

| Finding | Severity | File | Agent | Status | Notes |
|---------|----------|------|-------|--------|-------|
| F-003 | major | `frontend/src/pages/reports/ReportSchedules.tsx` | engineering-frontend-developer | fix applied | F-003 fixed. The toggle mutation now has its own `onSuccess` that only invalidates the `report-schedules` query. Toggling a schedule no longer closes an open edit or new-schedule form. `done` is still used for form saves only. |
