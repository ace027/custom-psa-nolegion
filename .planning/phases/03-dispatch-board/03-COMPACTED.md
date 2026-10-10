---
phase: 03-dispatch-board
compacted: 2026-10-10
original_summaries: [03-01-SUMMARY.md, 03-02-SUMMARY.md, 03-03-SUMMARY.md]
requirements_satisfied: [REQ-03]
---

# Phase 3: Dispatch board — Compacted Summary

## Deliverables
- 03-01 Library spike, scheduling API additions and pure board logic (Complete): backend/app/routers/scheduling.py, backend/app/scheduling.py, backend/app/scheduling_schemas.py, backend/tests/test_scheduling_api.py, docs/SCHEDULING.md, docs/verify/dispatch-spike.md, frontend/package-lock.json, frontend/package.json, frontend/src/scheduling/Spike.test.tsx, frontend/src/scheduling/api.ts, frontend/src/scheduling/board.test.ts, frontend/src/scheduling/board.ts, frontend/src/scheduling/zone.test.ts, frontend/src/scheduling/zone.ts
- 03-02 Dispatch board page (Complete with Warnings): docs/verify/dispatch-spike.md, frontend/src/App.tsx, frontend/src/Dispatch.test.tsx, frontend/src/pages/Dispatch.tsx, frontend/src/scheduling/BookingDialog.tsx, frontend/src/scheduling/EditDialog.tsx, frontend/src/scheduling/dispatch.css
- 03-03 Appointments on the ticket, timer start, and the Playwright booking flow (Complete)

## Decisions
- 03-01: backgroundBlocks takes a third argument, the visible range `{from, to}`. The plan's signature had none, but off-hours is the complement of the working windows w
- 03-01: moveSummary takes a fourth argument, `zone`, to format "Tue 14:00".
- 03-01: undoPatch always sends all three of tech_id, starts_at and ends_at from `before`. The `after` parameter is unused, so it is named `_after`.
- 03-02: Shading uses RBC `backgroundEvents`. They get `pointer-events: none`, so clicks and slot selection pass through and they can't be dragged.
- 03-03: The runner falls back to `$PLAYWRIGHT_BROWSERS_PATH/chromium` when Playwright's own browser build is missing and `CHROMIUM_PATH` is unset.
- 03-03: Each spec cancels the appointments it booked, so repeated runs start from the same board.
- 03-03: The card fetches conflicts with `getAppointment` for upcoming rows only, at most 10.

## Conventions and Open Questions
- 03-01 convention: Import `schedulingKeys` and the fetchers from `frontend/src/scheduling/api.ts`. Pass `withConflicts: true` to `listAppointments` for the board, with a range of 
- 03-01 convention: Board dates are fake-local. Convert with `toBoardDate`/`fromBoardDate` and the org zone (`getOrgTimezone`). Get ranges from `zoneDayRange`/`zoneWeekRange`.
- 03-01 convention: Call `moveSummary(before, after, staff, zone)`, `backgroundBlocks(rows, zone, {from, to})`, and `dropPatch(a, {start, end, resourceId}, zone)`.
- 03-02 convention: In Playwright, query the dialog's fields inside `getByRole('dialog')`, because week view also has a 'Tech' select. Field labels are Tech/Date/Start/End/Notes
- 03-02 convention: buttons are Save, Cancel appointment (then Confirm cancel), Close and Book. 'New booking' is the button that opens the booking dialog. The toast is role=status 
- 03-02 convention: failures appear in role=alert.
- 03-03 convention: `scripts/e2e.sh <spec> [flags]` runs any Playwright spec on a fresh DB and free ports.
- 03-03 convention: Use `CHROMIUM_PATH` to override the browser.
- 03-03 convention: The ticket page's Appointments card links to `/dispatch?view=day&date=YYYY-MM-DD`.

## Files Modified
| File | Change |
|------|--------|
| `backend/app/routers/scheduling.py` | 03-01: Library spike, scheduling API additions and pure board logic |
| `backend/app/scheduling.py` | 03-01: Library spike, scheduling API additions and pure board logic |
| `backend/app/scheduling_schemas.py` | 03-01: Library spike, scheduling API additions and pure board logic |
| `backend/tests/test_scheduling_api.py` | 03-01: Library spike, scheduling API additions and pure board logic |
| `docs/SCHEDULING.md` | 03-01: Library spike, scheduling API additions and pure board logic |
| `docs/verify/dispatch-spike.md` | 03-01: Library spike, scheduling API additions and pure board logic |
| `frontend/package-lock.json` | 03-01: Library spike, scheduling API additions and pure board logic |
| `frontend/package.json` | 03-01: Library spike, scheduling API additions and pure board logic |
| `frontend/src/scheduling/Spike.test.tsx` | 03-01: Library spike, scheduling API additions and pure board logic |
| `frontend/src/scheduling/api.ts` | 03-01: Library spike, scheduling API additions and pure board logic |
| `frontend/src/scheduling/board.test.ts` | 03-01: Library spike, scheduling API additions and pure board logic |
| `frontend/src/scheduling/board.ts` | 03-01: Library spike, scheduling API additions and pure board logic |
| `frontend/src/scheduling/zone.test.ts` | 03-01: Library spike, scheduling API additions and pure board logic |
| `frontend/src/scheduling/zone.ts` | 03-01: Library spike, scheduling API additions and pure board logic |
| `docs/verify/dispatch-spike.md` | 03-02: Dispatch board page |
| `frontend/src/App.tsx` | 03-02: Dispatch board page |
| `frontend/src/Dispatch.test.tsx` | 03-02: Dispatch board page |
| `frontend/src/pages/Dispatch.tsx` | 03-02: Dispatch board page |
| `frontend/src/scheduling/BookingDialog.tsx` | 03-02: Dispatch board page |
| `frontend/src/scheduling/EditDialog.tsx` | 03-02: Dispatch board page |
| `frontend/src/scheduling/dispatch.css` | 03-02: Dispatch board page |

## Verification
- 03-01 (REQ-03): 11/11 verification commands passed
- 03-02 (REQ-03): 5/5 verification commands passed
- 03-03 (REQ-03): 6/6 verification commands passed

## Agents
- 03-01: engineering-senior-developer
- 03-02: engineering-frontend-developer
- 03-03: engineering-senior-developer

## Also Covered
- frontend/src/pages/TicketAppointmentsCard.tsx
- frontend/src/pages/TicketDetail.tsx
- frontend/src/TicketAppointments.test.tsx
- frontend/vite.config.ts
- frontend/playwright.config.ts
- frontend/e2e/dispatch.spec.ts
- docs/DEVELOPMENT.md
- docs/verify/dispatch-board.md
