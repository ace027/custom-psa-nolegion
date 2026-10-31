# Phase 14: Portal polish — Review Fixes

Fixes applied by the review loop, one section per cycle. Re-review decides whether each one holds.

## Cycle 1

**Date**: 2026-10-31
**Checks**: 11/15 passed
**Files changed**: `backend/app/portal_files.py`, `backend/app/portal_schemas.py`, `backend/tests/test_portal_polish.py`, `frontend/src/portal/PortalApp.tsx`

| Finding | Severity | File | Agent | Status | Notes |
|---------|----------|------|-------|--------|-------|
| F-001 | major | `backend/app/portal_files.py (with backend/app/portal_schemas.py)` | engineering-senior-developer | not fixed | partial |
| F-002 | major | `frontend/src/portal/PortalApp.tsx` | engineering-frontend-developer | fix applied | F-002 fixed in Verify. A missing #token now sets a `missing` state, so the "This link cannot be used" card shows instead of "Signing you in…" forever. The status text now has role="status". I added no new test. |

## Cycle 2

**Date**: 2026-10-31
**Checks**: 15/15 passed
**Files changed**: `backend/app/portal_files.py`, `backend/app/portal_schemas.py`, `backend/app/routers/portal.py`, `backend/tests/test_portal_polish.py`, `frontend/src/portal/PortalApp.tsx`

| Finding | Severity | File | Agent | Status | Notes |
|---------|----------|------|-------|--------|-------|
| F-004 | major | `backend/app/portal_schemas.py (with backend/app/portal_files.py)` | engineering-senior-developer | fix applied | Added SizeLimitedRoute, a custom APIRoute for the portal upload route. It returns 413 from Content-Length before the body is read, and it counts bytes as chunked bodies stream in. The limit is max_attachment_bytes*4/3 + 1 KB. I removed the hardcoded 10 MB max_length from the schema, so the settings value now governs the cap. FastAPI reads the body before it solves dependencies, so a route dependency could not do this. That is why I used a route class. |
| F-005 | major | `backend/app/portal_files.py (with backend/app/portal_schemas.py and backend/app/routers/portal.py)` | engineering-senior-developer | fix applied | Added SizeLimitedRoute, a custom APIRoute for the portal upload route. It returns 413 from Content-Length before the body is read, and it counts bytes as chunked bodies stream in. The limit is max_attachment_bytes*4/3 + 1 KB. I removed the hardcoded 10 MB max_length from the schema, so the settings value now governs the cap. FastAPI reads the body before it solves dependencies, so a route dependency could not do this. That is why I used a route class. |
| F-006 | major | `frontend/src/portal/PortalApp.tsx` | engineering-frontend-developer | fix applied | F-006 fixed. The portal tab nav in PortalApp.tsx now has `flex-wrap`, so all 6 tabs stay reachable on narrow screens. I also added `aria-label="Portal sections"` to it. I made no other changes. |
