# Phase 2A verification: timers, internal time, weekly timesheet

Run the stack (`docker compose up`), sign in as an admin (or tech), then:

## Settings
1. Settings → **Internal time categories** lists Administration, Training, Meeting, Paid time off.
2. Add "Travel"; adding "travel" again is refused. Archive and restore it.

## Timer on a ticket
3. Open a ticket → Time card → choose a work type → **Start timer**. A blue bar with a ticking clock appears at the top of every page (try Organizations) and links back to the ticket.
4. Try **Start timer** on a second ticket: refused with "A timer is already running".
5. Click **Stop**. A normal time entry appears on the ticket (minutes rounded up, at least 1; billable minutes follow the usual increment rule).
6. Start another and click **Discard**: confirm; no time is saved.

## Internal time and timesheet
7. Sidebar → **My timesheet**. Log 60 minutes of Training; it shows in Entries and in the day total, counted as Internal, never billable.
8. Start an internal timer from the same page; Stop saves it as internal time.
9. Void an entry; it disappears from the sheet (kept in the audit log). Invoiced entries have no Void link.
10. Use Previous / Next / This week; weeks always begin on Monday.

## Permissions
11. A read-only user has no "My timesheet" link and the timer bar never shows. A tech cannot read another tech's sheet; an admin can (`GET /api/timesheet?week_start=YYYY-MM-DD&user_id=N`).

## Audit
12. Audit log shows `timer.start`, `timer.stop`, `timer.discard`, `internal_time.create/update/void`.

Automated: `backend/tests/test_timekeeping.py` (14 tests), `frontend/src/Phase2A.test.tsx`.
