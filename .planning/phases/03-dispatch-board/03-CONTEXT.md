# Phase 3: Dispatch board -- Context

## Phase Goal
A dispatcher books, moves and reassigns ticket appointments on a per-tech day/week drag-and-drop board.

## Requirements Covered
- REQ-03: Dispatch board. A per-tech day/week board with drag, resize and reassign, built on an MIT-licensed library. Conflict warnings for working hours, PTO and overlap. Each appointment shows on its ticket, and the existing timer can be started from an appointment.

## What Already Exists (from prior phases)
- Phase 2 scheduling API (backend/app/routers/scheduling.py, docs/SCHEDULING.md):
- - GET/POST /api/appointments; GET/PATCH /api/appointments/{id}; POST /api/appointments/{id}/cancel.
- - GET /api/availability: per user, the timezone, working windows, approved time off, scheduled appointment windows and free windows. At most 31 days and 50 user_ids.
- - GET /api/users/{id}/schedule.
- - AppointmentOut carries organization_name, ticket_number, ticket_subject, tech_name, starts_at, ends_at, status, notes, client_visible and conflicts[]. Each conflict has kind (outside_hours, time_off, time_off_pending or overlap), time_off_id and appointment_id.
- - The list endpoint currently returns conflicts=[]. Conflicts are computed only by the single GET, POST and PATCH.
- - Permissions: schedule:read (all roles), schedule:write (admin and tech), timeoff:approve (admin).
- - Conflicts are warnings only and never block.
- GET /api/settings (ticket:read) returns the org timezone.
- GET /api/users (user:read, all roles) lists staff with their role and active flag.
- Timer: POST /api/timer/start {ticket_id, work_type_id, billable, note}. It returns 409 when a timer is already running. TicketDetail.tsx TimeCard (~L363-420) starts it, and TimerBar.tsx shows the running timer.
- Frontend stack:
- - React 19.3, react-router-dom 7, @tanstack/react-query 5, Tailwind 4, vitest 5 (jsdom) and Playwright 1.63.
- - Routes live in src/App.tsx StaffApp and are gated by can(me, perm) from src/auth.tsx.
- - The API helper is api<T>(path, {json}) in src/api.ts.
- - Shared UI is in src/ui.tsx.
- - No date or calendar library is installed.
- Playwright specs:
- - They live in frontend/e2e/*.spec.ts and log in with the 'Email' field and the 'Dev login' button.
- - They need DEV_LOGIN_ENABLED=true and python -m app.seed.
- - They are not run in CI, and vite.config.ts hardcodes port 5173 and an /api proxy to localhost:8000.
- CI frontend job: npm ci, npm run typecheck, npm test (vitest run), npm run build. Backend CI: ruff check/format and pytest (needs Postgres; run `service postgresql start` locally first).

## Key Design Decisions
- Library: react-big-calendar (MIT) with its built-in drag-and-drop addon, plus date-fns and @date-fns/tz for the localizer and zones.
- The 03-01 spike must prove four things before 03-02 builds on the library:
- - npm install with no --legacy-peer-deps, no .npmrc override and no package.json overrides;
- - the MIT licence;
- - drag-and-drop with resources rendering under React 19 in vitest;
- - correct round-trips across zones and DST.
- If any spike check fails, the plan stops and escalates. Never work around it.
- Day view has one column per tech (RBC resources): every active user whose role is admin or tech, from GET /api/users.
- Week view shows one tech at a time (a tech picker) with 7 day columns.
- Board zone policy:
- - Day view renders in the org timezone (GET /api/settings).
- - Week view renders in the selected tech's effective timezone (GET /api/users/{id}/schedule .timezone).
- - A visible badge names the zone, for example 'Times in America/Chicago'.
- - UTC instants become wall-clock 'fake local' Dates for RBC and are converted back on drop. The API always gets ISO UTC.
- - Tooltips add the tech's local time when it differs from the board zone.
- Booking:
- - Select an empty slot to open a Book dialog that searches tickets.
- - Book from a 'Book' button on the ticket page.
- - A 'New booking' button opens the same dialog with tech, date, start and end fields. That is the keyboard route.
- - There is no unscheduled-ticket queue.
- Moves:
- - Drag, resize or drop on another tech's column PATCHes the appointment optimistically, rolls back on error, and then refetches.
- - Conflicts always come from the server response and are never computed on the client.
- - An Undo toast (8 seconds) names what changed, for example 'Moved to Sam'. Undo PATCHes the previous tech, start and end back.
- Conflict markers:
- - A persistent amber outline and a warning icon on the block, plus text labels in the tooltip and in the detail panel.
- - Labels: outside_hours 'Outside working hours', time_off 'During approved time off', time_off_pending 'During pending time off', overlap 'Overlaps another appointment'.
- - Never colour alone.
- Shading:
- - Off-hours: a neutral hatch.
- - Approved time off: a muted fill labelled 'Time off'.
- - Pending time off: a dashed outline labelled 'Pending'.
- - A legend explains them.
- Users without schedule:write see the board read-only (no drag, resize, select or booking buttons) with a 'View only' label.
- Every block opens an Edit dialog on click or Enter. It has tech, date, start and end fields, notes and Cancel appointment. It is the non-drag path for move, resize and reassign.
- The board route is lazy-loaded (React.lazy) so react-big-calendar and its CSS stay out of the main chunk.
- Backend additions (additive API changes):
- - GET /api/appointments?with_conflicts=true returns conflicts per item. It is only allowed when both from and to are given and the range is at most 8 days, otherwise 422.
- - AvailabilityOut gains time_off_pending: list[Window] (pending requests only).
- The timer starts from the ticket appointments card: POST /api/timer/start with the ticket_id and a work type picked in an inline select. The API's 409 text is shown as is.
- e2e:
- - scripts/e2e.sh creates an isolated database psa_e2e_$$, migrates and seeds it, starts uvicorn and Vite on free ports, runs the given Playwright specs with workers=1, and always drops the database and kills both processes.
- - vite.config.ts reads E2E_API_PORT for the proxy target (default 8000).
- - Specs pin the browser clock and assert outcomes through the API.
- - There is no CI e2e job (owner decision).

## Plan Structure
- **Plan 03-01 (Wave 1)**: Library spike, scheduling API additions and pure board logic -- Prove react-big-calendar with drag-and-drop works cleanly under React 19, add the two additive API fields the board needs, and build a typed scheduling client plus the pure zone and board logic with exhaustive vitest coverage.
- **Plan 03-02 (Wave 2)**: Dispatch board page -- Build the /dispatch page. It has a day view with one column per tech and a week view for one tech. Users can drag, resize and reassign appointments with optimistic updates and Undo, book from a slot or a dialog, edit through a keyboard-accessible dialog, and see persistent conflict markers and shading for working hours and time off.
- **Plan 03-03 (Wave 3)**: Appointments on the ticket, timer start, and the Playwright booking flow -- Show a ticket's appointments on its page with a Book button and Start timer, and add an isolated local e2e runner and Playwright specs that prove the booking flow end to end.
