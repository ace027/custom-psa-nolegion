# Phase 16: Front-end redesign (navigation and layout) — Review Fixes

Fixes applied by the review loop, one section per cycle. Re-review decides whether each one holds.

## Cycle 1

**Date**: 2026-11-02
**Checks**: 11/16 passed
**Files changed**: `backend/app/routers/config.py`, `frontend/src/App.tsx`, `frontend/src/Navigation.test.tsx`, `frontend/src/SettingsSplit.test.tsx`, `frontend/src/api.ts`, `frontend/src/lookups.ts`, `frontend/src/pages/admin/settings/TicketSettings.tsx`, `frontend/src/pages/crm/Leads.tsx`, `frontend/src/pages/crm/OpportunityPage.tsx`, `frontend/src/pages/quotes/QuotesList.tsx`, `frontend/src/scheduling/api.ts`

| Finding | Severity | File | Agent | Status | Notes |
|---------|----------|------|-------|--------|-------|
| F-001 | critical | `frontend/src/App.tsx` | engineering-frontend-developer | not fixed | partial |
| F-002 | major | `backend/app/ticket_services.py (the same gap is in /home/user/custom-psa-nolegion/frontend/src/scheduling/api.ts:172, /home/user/custom-psa-nolegion/frontend/src/lookups.ts:22, /home/user/custom-psa-nolegion/frontend/src/pages/crm/Leads.tsx:116 and /home/user/custom-psa-nolegion/frontend/src/pages/crm/OpportunityPage.tsx:117)` | engineering-frontend-developer | not fixed | partial |
| F-003 | major | `frontend/src/Navigation.test.tsx` | engineering-frontend-developer | not fixed | partial |
| F-004 | critical | `frontend/src/App.tsx` | engineering-frontend-developer | not fixed | partial |
| F-005 | major | `backend/app/routers/config.py, backend/app/routers/ticket_config.py, frontend/src/pages/admin/settings/TicketSettings.tsx` | engineering-frontend-developer | not fixed | partial |
