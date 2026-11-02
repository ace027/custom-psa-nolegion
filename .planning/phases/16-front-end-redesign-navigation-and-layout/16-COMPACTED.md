---
phase: 16-front-end-redesign-navigation-and-layout
compacted: 2026-11-02
original_summaries: [16-01-SUMMARY.md, 16-02-SUMMARY.md, 16-03-SUMMARY.md, 16-04-SUMMARY.md]
requirements_satisfied: []
---

# Phase 16: Front-end redesign (navigation and layout) — Compacted Summary

## Deliverables
- 16-01 Permission split and manager role (Complete)
- 16-02 Icon rail, All pages and reorderable per-user bookmarks (Complete): backend/alembic/versions/0040_user_nav_bookmarks.py, backend/app/models.py, backend/app/routers/auth.py, backend/app/schemas.py, backend/tests/test_nav_bookmarks.py, backend/tests/test_seed_and_migrations.py, docs/api/openapi.json, frontend/src/App.tsx, frontend/src/Bookmarks.test.tsx, frontend/src/Navigation.test.tsx, frontend/src/api.ts, frontend/src/nav/AdminLayout.tsx, frontend/src/nav/AllPages.tsx, frontend/src/nav/Rail.tsx, frontend/src/nav/navConfig.ts, frontend/src/nav/useBookmarks.ts
- 16-03 Settings split into Admin sub-pages (Complete): frontend/src/App.tsx, frontend/src/SettingsSplit.test.tsx, frontend/src/nav/navConfig.ts, frontend/src/pages/Settings.tsx, frontend/src/pages/admin/settings/BillingSettings.tsx, frontend/src/pages/admin/settings/GeneralSettings.tsx, frontend/src/pages/admin/settings/MailCalendarSettings.tsx, frontend/src/pages/admin/settings/PortalSettings.tsx, frontend/src/pages/admin/settings/SalesSettings.tsx, frontend/src/pages/admin/settings/SchedulingSettings.tsx, frontend/src/pages/admin/settings/TicketSettings.tsx
- 16-04 Command palette (Complete): frontend/src/App.tsx, frontend/src/CommandPalette.test.tsx, frontend/src/nav/CommandPalette.tsx, frontend/src/nav/Rail.tsx

## Decisions
- 16-01: The client billing card is hidden as a whole without `invoice:read`, because routes that mix catalog and invoice data use `invoice:read`.
- 16-02: The bookmarks endpoints live at /api/v1/me/* as the plan says. Because the auth router has the /auth prefix, auth.py now exports a combined `router` (auth_route
- 16-03: The sub-pages are not added to NAV_ITEMS. Navigation.test.tsx asserts the exact All pages list per role and the Admin sub-nav labels, and I can't edit that file
- 16-03: Settings has its own sub-nav ("Settings pages") inside /admin/settings.
- 16-03: A hand-typed URL to a page the role lacks redirects to /admin/settings.
- 16-04: The plan says to use "the existing ticket-number lookup in api.ts", but api.ts has none. I used `GET /tickets?q=N&limit=5` (the backend matches a number exactly
- 16-04: A ticket the user cannot see, a missing one and a failed lookup all show "Ticket #N not found" as a disabled option. This covers 404s as well as empty results.
- 16-04: Quick actions only navigate: New ticket to /tickets, Start a timer to /timesheet, Book an appointment to /dispatch, New quote to /quotes, Record a payment to /b

## Conventions and Open Questions
- 16-01 convention: Front-end navigation should gate finance on `invoice:read`, procurement on `procurement:read` and service settings on `service:configure`
- 16-01 convention: manager is a valid role in the API, the database and the Users page.
- 16-02 convention: For 16-04, `NAV_ITEMS` has keywords for the palette
- 16-02 convention: `useBookmarks` exposes toggle, move, remove, isBookmarked, status and error and is created once in App.tsx's Layout. The rail "Go to" button already has `aria-k
- 16-02 convention: replace the `onGoTo` prop in App.tsx with the palette opener.
- 16-03 convention: SETTINGS_PAGES and settingsPages(me) in navConfig.ts list the settings sub-pages. The command palette (16-04) can include them if wanted. itemForPath maps /admi
- 16-03 convention: SimpleList is exported from TicketSettings.tsx and reused by BillingSettings.tsx.
- 16-04 convention: The palette is `CommandPalette({ me, bookmarks, open, onClose })`, mounted in `Layout`. It records the last 4 visited nav ids in sessionStorage key `psa.recent-
- 16-04 convention: If a later wave gives a page a "create" query parameter, update the `ACTIONS` routes in `CommandPalette.tsx`.

## Files Modified
| File | Change |
|------|--------|
| `backend/alembic/versions/0040_user_nav_bookmarks.py` | 16-02: Icon rail, All pages and reorderable per-user bookmarks |
| `backend/app/models.py` | 16-02: Icon rail, All pages and reorderable per-user bookmarks |
| `backend/app/routers/auth.py` | 16-02: Icon rail, All pages and reorderable per-user bookmarks |
| `backend/app/schemas.py` | 16-02: Icon rail, All pages and reorderable per-user bookmarks |
| `backend/tests/test_nav_bookmarks.py` | 16-02: Icon rail, All pages and reorderable per-user bookmarks |
| `backend/tests/test_seed_and_migrations.py` | 16-02: Icon rail, All pages and reorderable per-user bookmarks |
| `docs/api/openapi.json` | 16-02: Icon rail, All pages and reorderable per-user bookmarks |
| `frontend/src/App.tsx` | 16-02: Icon rail, All pages and reorderable per-user bookmarks |
| `frontend/src/Bookmarks.test.tsx` | 16-02: Icon rail, All pages and reorderable per-user bookmarks |
| `frontend/src/Navigation.test.tsx` | 16-02: Icon rail, All pages and reorderable per-user bookmarks |
| `frontend/src/api.ts` | 16-02: Icon rail, All pages and reorderable per-user bookmarks |
| `frontend/src/nav/AdminLayout.tsx` | 16-02: Icon rail, All pages and reorderable per-user bookmarks |
| `frontend/src/nav/AllPages.tsx` | 16-02: Icon rail, All pages and reorderable per-user bookmarks |
| `frontend/src/nav/Rail.tsx` | 16-02: Icon rail, All pages and reorderable per-user bookmarks |
| `frontend/src/nav/navConfig.ts` | 16-02: Icon rail, All pages and reorderable per-user bookmarks |
| `frontend/src/nav/useBookmarks.ts` | 16-02: Icon rail, All pages and reorderable per-user bookmarks |
| `frontend/src/App.tsx` | 16-03: Settings split into Admin sub-pages |
| `frontend/src/SettingsSplit.test.tsx` | 16-03: Settings split into Admin sub-pages |
| `frontend/src/nav/navConfig.ts` | 16-03: Settings split into Admin sub-pages |
| `frontend/src/pages/Settings.tsx` | 16-03: Settings split into Admin sub-pages |
| `frontend/src/pages/admin/settings/BillingSettings.tsx` | 16-03: Settings split into Admin sub-pages |
| `frontend/src/pages/admin/settings/GeneralSettings.tsx` | 16-03: Settings split into Admin sub-pages |
| `frontend/src/pages/admin/settings/MailCalendarSettings.tsx` | 16-03: Settings split into Admin sub-pages |
| `frontend/src/pages/admin/settings/PortalSettings.tsx` | 16-03: Settings split into Admin sub-pages |
| `frontend/src/pages/admin/settings/SalesSettings.tsx` | 16-03: Settings split into Admin sub-pages |
| `frontend/src/pages/admin/settings/SchedulingSettings.tsx` | 16-03: Settings split into Admin sub-pages |
| `frontend/src/pages/admin/settings/TicketSettings.tsx` | 16-03: Settings split into Admin sub-pages |
| `frontend/src/App.tsx` | 16-04: Command palette |
| `frontend/src/CommandPalette.test.tsx` | 16-04: Command palette |
| `frontend/src/nav/CommandPalette.tsx` | 16-04: Command palette |
| `frontend/src/nav/Rail.tsx` | 16-04: Command palette |

## Verification
- 16-01: 8/8 verification commands passed
- 16-02: 6/7 verification commands passed
- 16-03: 3/4 verification commands passed
- 16-04: 4/4 verification commands passed

## Agents
- 16-01: engineering-security-engineer
- 16-02: engineering-frontend-developer
- 16-03: engineering-frontend-developer
- 16-04: engineering-frontend-developer

## Also Covered
- backend/app/permissions.py
- backend/app/routers/invoices.py
- backend/app/routers/payments.py
- backend/app/routers/notices.py
- backend/app/routers/credit_memos.py
- backend/app/routers/late_fees.py
- backend/app/routers/billing.py
- backend/app/routers/reports.py
- backend/app/routers/crm.py
- backend/app/routers/ticket_config.py
- backend/app/routers/holidays.py
- backend/app/routers/config.py
- backend/app/routers/procurement.py
- backend/app/routers/users.py
- backend/alembic/versions/0039_manager_role_and_permission_split.py
- backend/tests/test_role_matrix.py
- backend/tests/test_zz_api_contract.py
- backend/tests/conftest.py
- frontend/src/pages/Users.tsx
- frontend/src/pages/OrganizationDetail.tsx
- frontend/src/pages/OrgBillingCard.tsx
- frontend/src/pages/billing/
- backend/app/ticket_services.py
- backend/app/scheduling.py
- frontend/src/Billing.test.tsx
- frontend/src/Payments.test.tsx
- frontend/src/Phase3B.test.tsx
- frontend/src/Phase3C.test.tsx
- frontend/src/Reminders.test.tsx
- frontend/src/Procurement.test.tsx
