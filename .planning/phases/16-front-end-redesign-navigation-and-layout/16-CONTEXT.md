# Phase 16: Front-end redesign (navigation and layout) -- Context

## Phase Goal
Staff find what they need without scanning a long sidebar: move the app to mockup C (icon rail of per-user bookmarks that can be reordered at any time, an All pages panel grouped by section, and a Ctrl/Cmd+K command palette), with role access following the owner's decisions and enforced by the API.

## Requirements Covered
- Owner test note 4: too many options in the left sidebar
- Navigation per .planning/designs/16-navigation/DECISIONS.md: mockup C (rail + All pages + palette), bookmarks per user on the server and reorderable by drag, menu or keyboard without unpinning; finance hidden from techs and read-only; manager role; Users admin-only; Settings split into Admin sub-pages
- Every existing page stays reachable; old URLs redirect
- Keyboard and screen-reader navigation; works at 1280px and tablet width

## What Already Exists (from prior phases)
- frontend/src/App.tsx: Layout with a flat sidebar of NavLinks gated by can(me, perm); /me returns the role's permission list (backend/app/routers/auth.py from permissions.MATRIX)
- backend/app/permissions.py: ROLES admin/tech/billing/read_only, MATRIX, default deny; users.role CHECK constraint ck_users_role from migration 0001
- frontend/src/pages/Settings.tsx: one long page of ~22 settings cards over the existing settings API
- Mockups and comparison in .planning/designs/16-navigation/ (mockup-c.html is the target layout, chosen 2026-11-02 over A; README.md maps every current nav item to its new place)
- Knowledge base removed and replaced by Hudu article suggestions (migration 0037); there is no KB nav entry
- API keys carry explicit permission lists (KEY_FORBIDDEN in permissions.py)

## Key Design Decisions
- Layout: mockup C (owner changed from A on 2026-11-02): left icon rail with Go to, the user's bookmarks (up to 8, role defaults until changed), All pages, profile/theme; bottom tab bar under 768px. All pages groups every allowed page by section (Service desk, Scheduling, Clients & sales, Finance, Reports, Admin) with a star per page.
- Bookmarks: reorderable at any time without unpinning (drag and drop, item menu Move up/Move down/Remove, Alt+ArrowUp/Down), announced and saved; stored per user on the server (users.nav_bookmarks, migration 0040, GET/PUT /api/v1/me/bookmarks, own row only, API keys 403).
- One typed nav config (frontend/src/nav/navConfig.ts: section, label, route, required permission, keywords) drives the sidebar, the admin sub-nav, the palette and the tests (board recommendation).
- Permissions: billing:read keeps the catalog (products, rates, agreements, ticket charges); new invoice:read covers invoices, runs, payments, statements, notices/reminders, credit memos, write-offs, late fees, receivables; new service:configure covers queues, categories, priorities, statuses, work types, SLA, holidays; config:manage keeps the general settings (mail, billing, portal, security).
- Roles: admin = everything incl. invoice:read and service:configure. billing = unchanged + invoice:read. tech = loses procurement:read/write and has no invoice:read. read_only = org, user, ticket, billing (catalog), quote, schedule, crm reads only. New manager = tech's permissions minus procurement + timesheet:approve, timeoff:approve, report:read, audit:read, invoice:read, service:configure; no billing:write/finalize, payment:write, user:manage, integration:manage, apikey:manage, automation:manage, portal:manage, config:manage.
- Existing API keys that hold billing:read get invoice:read added by the migration, and keys holding config:manage get service:configure, so no integration silently loses access.
- Users page is admin-only in the nav; user:read stays for every role (pickers).
- Labels stay 'Organizations' and 'Sales'; billing reports stay under Billing with a link from Reports.
- Old URLs (/settings, /users and any moved route) redirect to their new location; removed KB URLs (/kb, /kb/*) redirect to /tickets.
- Architecture proposals: skipped (decisions already made by the owner from the mockups).

## Plan Structure
- **Plan 16-01 (Wave 1)**: Permission split and manager role -- Split billing:read and config:manage as decided, remove procurement and invoices from techs and read-only, add the manager role end to end, enforced by the API with a role-by-endpoint test matrix.
- **Plan 16-02 (Wave 2)**: Icon rail, All pages and reorderable per-user bookmarks -- mockup C's rail and All pages panel from one typed nav config, server-stored bookmarks reorderable by drag, menu or keyboard, Admin sub-nav, redirects.
- **Plan 16-03 (Wave 3)**: Settings split into Admin sub-pages -- Split the long Settings page into Admin sub-pages, each gated by the permission that edits it, with no change to the settings API or saved values.
- **Plan 16-04 (Wave 4)**: Command palette -- Ctrl/Cmd+K palette: any allowed page or tab, ticket-number jump, quick actions, Bookmarked/Recent/Actions when empty, Alt+P to bookmark.
