# Design Exploration — Scheduling & Dispatch (Parity Phase 4)

## Initial Ask
Explore the next parity phase after billing depth (phases 1, 2 and 3A–3C are built on `dev`). The
pick was **Scheduling & dispatch** from `docs/PARITY_ROADMAP.md` phase 4: technician calendar,
appointments tied to tickets, availability, on-call, Outlook calendar sync.

## Research Summary

### Facts
- No scheduling exists. `User` (`backend/app/models.py:107-123`) has no timezone, working hours or
  PTO. No appointment model, no `Calendars` Graph scope anywhere in the repo.
- Org-wide business hours and timezone live in the single `Settings` row
  (`backend/app/models.py:236-277`). Org-wide `Holiday` table (`models.py:280-289`,
  `backend/app/routers/holidays.py`). Business-minute math is pure functions in `backend/app/sla.py`
  (`Calendar`, `add_business_minutes`, `compute_due_dates`).
- Tickets have `assignee_id` (`models.py:328`); `_check_assignee` in `backend/app/ticket_services.py:57`
  allows only active admin/tech. Timers and time entries exist (`models.py:400,437`,
  `frontend/src/pages/TimerBar.tsx`).
- `TicketEscalation` (once per ticket on SLA breach) and email `notifications.py` exist; the user
  has `notify_*` flags.
- Graph is app-only client credentials (`backend/app/mail/graph.py:86-122`), run only in the worker
  (`backend/app/worker.py`; jobs `billing_jobs`, `notify_jobs`, `integration_jobs`, mail
  `run_cycle`). The app is scoped to one mailbox with Exchange RBAC for Applications and has **no**
  Entra Graph API permissions (`docs/MAIL_SETUP.md`). Test fakes: `backend/dev/fake_graph.py`,
  `backend/tests/mailfakes.py`, `backend/tests/test_graph_client.py`.
- Permissions: `backend/app/permissions.py`, roles admin/tech/billing/read_only, no scheduling
  permissions yet.
- Conventions (`docs/DEVELOPMENT.md`, `CLAUDE.md`): new Alembic revision only; writes through
  `services.py` with `audit.record`; client-owned tables need `organization_id`, an RLS policy and an
  isolation test; every route needs summary/tag/permission/test (`test_zz_api_contract.py`).
  Auth/permissions, RLS and migrations stay with the main model.
- Frontend: React 19, react-router 7, react-query 5, Tailwind 4, Vite 8. No date or calendar library.
- Graph: creating/updating/deleting `/users/{id}/events` needs `Calendars.ReadWrite` (application)
  (learn.microsoft.com/graph/api/event-update, permissions-reference). Exchange RBAC for Applications
  replaces Application Access Policies and scopes an app to a mailbox group
  (learn.microsoft.com/graph/auth-limit-mailbox-access). `getSchedule` returns free/busy in UTC,
  interval 5–1440 min (learn.microsoft.com/graph/api/calendar-getschedule).
- FullCalendar Standard is MIT. Its resource timeline and vertical resource views are Premium
  (from $480) (fullcalendar.io/pricing).

### Inferences
- Availability math belongs next to `sla.py` as pure functions and can reuse `Holiday`. PTO needs its
  own table.
- Outlook sync belongs in the worker, which keeps the boundary that only the worker holds the Graph
  secret.
- The board needs per-tech columns without Premium, so it needs an MIT library with resource support
  or a custom layout.
- One `getSchedule` call covers a 1–10 tech team, so polling is cheap.

### Assumptions (unverified)
- react-big-calendar and Schedule-X are MIT, maintained, and work with React 19 drag-and-drop.
- RBAC for Applications offers an `Application Calendars.ReadWrite` role, and `getSchedule` honours
  RBAC-scoped grants.
- Dispatch practices in Autotask, HaloPSA and ConnectWise were not checked.

## Product Definition
- **Target users:** the dispatcher or admin booking work, and techs (1–10) seeing and running
  their day. Clients get booking confirmations.
- **Primary outcome:** dispatch ticket work into a tech's day and see at a glance who is free.
- **Value proposition:** one board showing ticket bookings, working hours, PTO, on-call and Outlook
  busy time. Bookings appear in each tech's Outlook automatically. The PSA remains the source of
  truth.
- **Non-goals (this phase):** inbound sync of Outlook edits; Graph webhooks/subscriptions;
  recurring appointments; slot auto-suggestion or skills matching; SLA changes from bookings;
  automatic time entries or billing from appointments; paid calendar libraries.

## Recommended Approach
**B — Balanced.** The PSA is the system of record. Each appointment write bumps a desired version in
an outbox row, in the same transaction and audited. A worker `calendar_jobs()` pushes it to the
tech's Outlook (POST/PATCH/DELETE `/users/{id}/events`). It is idempotent through `transactionId` and
an extended property `psa-appointment-id`, and it treats 404 on PATCH/DELETE as done. Retries and the
failed state follow the mail pattern. The worker polls `getSchedule` about every 5 min into a
`busy_blocks` cache. The API never calls Graph. The board uses an MIT library with per-tech columns.

## Alternatives Considered
| Approach | Strengths | Tradeoffs | Decision |
|---|---|---|---|
| A: Conservative (PSA-only calendar, `.ics` email invites) | No permission change; smallest build | No free/busy; invites clutter inboxes; misses the one-way push decision | Rejected; fallback if the Graph scope change is refused |
| B: Balanced (worker outbox push + free/busy cache, MIT board) | Meets every decision; keeps the worker-only Graph boundary; reuses outbox/retry and pure-math patterns; slices ship independently | Needs RBAC-scoped `Calendars.ReadWrite`; free/busy up to ~5 min stale; Outlook-side edits overwritten on next push | **Chosen** |
| C: Ambitious (B + webhooks, recurrence, slot suggestions) | Closest to commercial PSAs | Public webhook endpoint in the API; breaks the worker-only Graph rule; about twice the size; edges into inbound sync | Deferred to a later phase |

## Feature Scope

### MVP
- [ ] 4A: Per-tech IANA timezone (defaults to the Settings timezone), weekly working hours, PTO, the
      `appointments` model (ticket-linked, org-scoped with RLS and isolation test), and pure
      availability math. Includes API and scheduling permissions.
- [ ] 4B: Spike to confirm the MIT board library works with React 19 drag-and-drop. Then a per-tech
      day/week dispatch board with drag, resize and reassign; conflict warnings for working hours,
      PTO and overlap; the appointment shown on its ticket; and "start timer" from an appointment.
- [ ] 4C: Spike to confirm RBAC-scoped `Calendars.ReadWrite` and `getSchedule` on a real tenant.
      Then the worker outbox push, the `getSchedule` busy cache, `fake_graph` endpoints for events
      and `getSchedule`, and failed-sync visibility on the board and Settings.
- [ ] 4D: Client confirmation and reschedule emails, a portal appointments view, on-call rotations
      with overrides, and a "who's on call" display.

### Later
- [ ] Graph change notifications and Outlook-side deletion detection
- [ ] Recurring appointments
- [ ] Slot suggestions and skills
- [ ] On-call driving SLA escalation, if not taken in v1
- [ ] Survey visits from quoting as appointments (`docs/BACKLOG.md`)

## Experience / Workflow
1. A dispatcher opens a ticket or the board and drags the ticket, or uses "Book", onto a tech's
   column at a time.
2. The board shows working hours, PTO, on-call and Outlook busy blocks. A warning appears if the
   slot conflicts.
3. Saving creates the appointment and audits it. The worker pushes it to the tech's Outlook within
   one cycle. The client contact gets a confirmation email, and the visit shows in the portal.
4. Moving or reassigning the appointment updates or moves the Outlook event and emails a
   reschedule notice. Cancelling deletes the event.
5. The tech opens their day, opens the appointment and starts the existing timer from it. Time is
   logged as today.
6. Failed pushes show a count on the board and Settings, with the last error.

## Technical Direction
- **Backend:** new Alembic revision. Tables `appointments` (organization_id, ticket_id, tech
  link, starts_at/ends_at timestamptz, status, notes, client_visible), `user_schedules`,
  `user_time_off`, `oncall_rotations` + `oncall_shifts`, `appointment_sync` (outbox: graph_event_id,
  desired/synced version, state, attempts, last_error), `busy_blocks` (cache with no subject text),
  and `users.timezone`. Writes go through services with `audit.record`, queries through repositories
  with `Scope`. New permissions in `permissions.py`.
- **Availability math:** pure functions beside `sla.py`, with DST property tests.
- **Worker:** `calendar_jobs()` alongside the existing jobs, with one commit per unit of work and
  backoff then `failed`, matching the mail pattern.
- **Graph:** keep app-only. Add an Exchange RBAC assignment for calendars scoped to a "PSA Techs"
  group, with still no Entra Graph permissions. Update `docs/MAIL_SETUP.md` and add a calendar
  setup doc.
- **Frontend:** react-big-calendar (MIT, `resources` for per-tech columns) after the spike. Schedule-X
  is the fallback and a custom grid the last resort. Possibly one date/timezone dependency.
- **Tests:** pytest on real Postgres, isolation tests for every new client-owned table, fake Graph
  for event and `getSchedule` flows, vitest for board logic, and Playwright for booking.

## Open Questions
| # | Question | Resolution path |
|---|---|---|
| 1 | Approve RBAC-scoped `Application Calendars.ReadWrite` for tech mailboxes? | Owner decision before 4C; confirm in the 4C spike on a real tenant; if refused, use approach A's `.ics` invites |
| 2 | Should on-call notify on SLA breach escalation, or display only in v1? | Owner decision at `/triad:plan` for 4D; default display only |
| 3 | What may an Outlook event show (client, subject, site address)? Mark events private? | Owner decision before 4C; default ticket number + link, marked private |
| 4 | Client confirmation: notify only or accept/decline in the portal? Which contact? | Owner decision before 4D; default notify-only to the ticket contact |
| 5 | Can techs book or move other techs' appointments? What do billing/read_only see? | Owner decision in the 4A permissions plan (main model) |
| 6 | Conflicts: warn only or block, with admin override? | Owner decision before 4B; default warn only |
| 7 | PTO: self-serve or admin-approved? | Owner decision before 4A |
| 8 | Is a first date/timezone dependency (`date-fns-tz` or similar) acceptable? | Escalate as an unplanned dependency at 4B planning |
| 9 | Multiple techs per appointment in v1? | Owner decision before 4A (decides `tech_id` column vs join table) |
| 10 | Are the react-big-calendar licence and React 19 support confirmed? | 4B spike |

## Start Input
Parity phase 4, Scheduling & dispatch, for a 1–10 tech MSP PSA (FastAPI/Postgres RLS/React).
Outcome: dispatch ticket work to techs on a per-tech day/week drag-and-drop board, with per-tech
timezone, working hours, PTO, on-call rotation, client confirmation emails and a portal view.
Outlook gets a one-way push of bookings to each tech's calendar from the worker through an
idempotent outbox, plus a `getSchedule` free/busy cache. There is no inbound sync, and the API never
calls Graph. MIT-only calendar library (react-big-calendar after a spike). Appointments link to
tickets and can start the existing timer, with no SLA or billing effects. Slices: 4A availability +
model, 4B board, 4C Outlook push + free/busy, 4D client + on-call. Owner decisions are listed in Open
Questions; the Graph permission scope change (Q1) gates 4C.
