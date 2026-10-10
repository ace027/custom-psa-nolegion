# Phase 2: Scheduling: availability & appointments -- Context

## Phase Goal
Techs have a timezone, working hours and PTO, and staff can create ticket-linked appointments with availability checks via the API.

## Requirements Covered
- REQ-02: Scheduling foundation: per-tech IANA timezone, weekly working hours, PTO, ticket-linked appointments (org-scoped with RLS), pure availability math, API and scheduling permissions.

## What Already Exists (from prior phases)
- Org-wide Settings (timezone, business_days, business_start/end_minute) and Holiday (on_date, open_minute, close_minute; both null = closed) in backend/app/models.py; SLA business-minute math as pure functions in backend/app/sla.py (Calendar, _at for DST-correct local->UTC).
- RLS: app_org_visible(organization_id) policy named org_scope, ENABLE + FORCE ROW LEVEL SECURITY, grants to APP_ROLE (see backend/alembic/versions/0021_credit_memos_refunds.py ~297-304); tests/test_isolation.py rls_gaps() automatically fails for any table with organization_id lacking forced RLS + org_scope.
- Permissions in backend/app/permissions.py (string constants + MATRIX per role admin/tech/billing/read_only); routes use require(P.X) from app.deps; tests/test_zz_api_contract.py requires summary, tag, permission and a hit by the suite for every route.
- Ticket.assignee_id and ASSIGNABLE_ROLES = ('admin','tech') in backend/app/ticket_services.py; Ticket.organization_id is nullable (unsorted email tickets).
- Services write through ctx.db with audit.record; repositories filter with Scope.apply(stmt, Model.organization_id); conftest fixtures login(role), admin, make_org, make_ticket, make_org_with_ticket, owner (owner DB connection).

## Key Design Decisions
- Owner decision: PTO is request + admin approval. Techs request their own (pending); admins approve/reject; admin-entered PTO is approved immediately. Only approved PTO blocks availability; pending PTO shows as a 'time_off_pending' conflict.
- Owner decision: one tech per appointment (appointments.tech_id column, no join table).
- Owner decision: admins and techs can book, move and cancel any tech's appointments; billing and read_only can only view schedules.
- Permissions: schedule:read (all roles, added to _READ), schedule:write (admin, tech), timeoff:approve (admin).
- Conflicts are warnings only (never block a write) and are returned on appointment create/get/update: outside_hours, time_off, time_off_pending, overlap.
- Appointments require a ticket that has an organization and is not closed; organization_id is copied from the ticket and kept in sync by a composite FK (ticket_id, organization_id) -> tickets(id, organization_id) ON UPDATE CASCADE.
- appointments is client-owned: organization_id NOT NULL, forced RLS, org_scope policy, no DELETE grant (cancel instead). user_work_hours and user_time_off are staff tables (no organization_id, no RLS).
- Working hours: one window per weekday per user; a user with no rows uses the org business hours from Settings; users.timezone NULL means the Settings timezone.
- Org holidays apply on the tech's local calendar date, only on the tech's working days: closed day removes the window, a shortened day intersects it.
- Appointment length 1 minute to 24 hours; time-off length up to 366 days; all API datetimes must be timezone-aware (naive -> 422).
- No new dependencies: DST property tests are exhaustive parametrized loops over every day of a year in several zones (hypothesis is not installed).
- PTO reason is visible only to the PTO owner and admins; other viewers get reason null.
- No frontend in this phase (the board is phase 3).

## Plan Structure
- **Plan 02-01 (Wave 1)**: Scheduling schema, RLS and permissions -- Add migration 0024 with users.timezone, user_work_hours, user_time_off and the client-owned appointments table (forced RLS), the matching SQLAlchemy models, and the scheduling permissions.
- **Plan 02-02 (Wave 1)**: Pure availability math -- Add backend/app/availability.py: pure, DB-free functions that build a tech's working windows (timezone, weekly hours, org holidays), subtract busy intervals, and classify conflicts for a slot, with exhaustive DST tests.
- **Plan 02-03 (Wave 2)**: Scheduling services and API -- Add the scheduling service and routes: per-user timezone and working hours, the time-off request/approval workflow, ticket-linked appointments with conflict warnings, and an availability endpoint, all audited and permission-guarded, plus docs.
