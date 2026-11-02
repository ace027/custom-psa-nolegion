# Phase 16: Front-end redesign (navigation and layout) -- Context

## Phase Goal
Staff find what they need without scanning a long sidebar: move the app to mockup A (grouped, collapsible sidebar) plus a command palette, with role access following the owner's decisions and enforced by the API.

## Requirements Covered
- Owner test note 4: too many options in the left sidebar
- Navigation per .planning/designs/16-navigation/DECISIONS.md: mockup A + command palette; finance hidden from techs and read-only; manager role; Users admin-only; Settings split into Admin sub-pages
- Every existing page stays reachable; old URLs redirect
- Keyboard and screen-reader navigation; works at 1280px and tablet width

## What Already Exists (from prior phases)
- frontend/src/App.tsx: Layout with a flat sidebar of NavLinks gated by can(me, perm); /me returns the role's permission list (backend/app/routers/auth.py from permissions.MATRIX)
- backend/app/permissions.py: ROLES admin/tech/billing/read_only, MATRIX, default deny; users.role CHECK constraint ck_users_role from migration 0001
- frontend/src/pages/Settings.tsx: one long page of ~22 settings cards over the existing settings API
- Mockups and comparison in .planning/designs/16-navigation/ (mockup-a.html is the target layout; README.md maps every current nav item to its new place)
- Knowledge base removed and replaced by Hudu article suggestions (migration 0037); there is no KB nav entry
- API keys carry explicit permission lists (KEY_FORBIDDEN in permissions.py)

## Key Design Decisions
- Layout: mockup A grouped collapsible sidebar (sections such as Service desk, Scheduling, Clients, Sales, Finance, Insights, Admin) + Ctrl/Cmd+K command palette from mockup C; no pins.
- One typed nav config (frontend/src/nav/navConfig.ts: section, label, route, required permission, keywords) drives the sidebar, the admin sub-nav, the palette and the tests (board recommendation).
- Permissions: billing:read keeps the catalog (products, rates, agreements, ticket charges); new invoice:read covers invoices, runs, payments, statements, notices/reminders, credit memos, write-offs, late fees, receivables; new service:configure covers queues, categories, priorities, statuses, work types, SLA, holidays; config:manage keeps the general settings (mail, billing, portal, security).
- Roles: admin = everything incl. invoice:read and service:configure. billing = unchanged + invoice:read. tech = loses procurement:read/write and has no invoice:read. read_only = org, user, ticket, billing (catalog), quote, schedule, crm reads only. New manager = tech's permissions minus procurement + timesheet:approve, timeoff:approve, report:read, audit:read, invoice:read, service:configure; no billing:write/finalize, payment:write, user:manage, integration:manage, apikey:manage, automation:manage, portal:manage, config:manage.
- Existing API keys that hold billing:read get invoice:read added by the migration, and keys holding config:manage get service:configure, so no integration silently loses access.
- Users page is admin-only in the nav; user:read stays for every role (pickers).
- Labels stay 'Organizations' and 'Sales'; section open/closed state is per browser (localStorage); billing reports stay under Billing with a link from Reports.
- Old URLs (/settings, /users and any moved route) redirect to their new location; removed KB URLs (/kb, /kb/*) redirect to /tickets.
- Architecture proposals: skipped (decisions already made by the owner from the mockups).

## Plan Structure
- **Plan 16-01 (Wave 1)**: Permission split and manager role -- Split billing:read and config:manage as decided, remove procurement and invoices from techs and read-only, add the manager role end to end, enforced by the API with a role-by-endpoint test matrix.
- **Plan 16-02 (Wave 2)**: Grouped sidebar navigation shell -- Replace the flat sidebar with mockup A's grouped, collapsible sidebar driven by one typed nav config, with an Admin area (sub-nav) and redirects for moved and removed URLs.
- **Plan 16-03 (Wave 3)**: Settings split into Admin sub-pages -- Split the long Settings page into Admin sub-pages, each gated by the permission that edits it, with no change to the settings API or saved values.
- **Plan 16-04 (Wave 4)**: Command palette -- Add a Ctrl/Cmd+K command palette that jumps to any page the user can open, to a ticket by number, and runs a few quick actions.
