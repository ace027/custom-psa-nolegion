# Plan 04-04 Summary: Board Outlook busy shading, sync badges, settings card and setup docs

## Result
**Status**: Complete
**Wave**: 4
**Agent**: engineering-frontend-developer
**Completed**: 2026-10-10

## Agent Selection Rationale

| Candidate | Semantic | Heuristic | Memory | Total | Source |
|-----------|----------|-----------|--------|-------|--------|
| engineering-frontend-developer | — | 4 | 4 | 8 | mandatory |
| testing-qa-verification-specialist | — | 17 | 4.33 | 21.33 | heuristic |
| engineering-backend-architect | — | 15 | 3.86 | 18.86 | heuristic |

- **Task type detected**: implementation
- **Confidence**: LOW
- **Adapter**: claude-code
- **Model tier**: sonnet

## Completed Tasks
- [x] Task 1: Board busy shading and cache age (done)
- [x] Task 2: Sync badges, retry and the settings card (done)
- [x] Task 3: Dev-server check and calendar setup docs (done)

## Files Modified
- `docs/CALENDAR_SETUP.md`
- `docs/MAIL_SETUP.md`
- `frontend/e2e/dispatch.spec.ts`
- `frontend/src/OutlookSync.test.tsx`
- `frontend/src/pages/Dispatch.tsx`
- `frontend/src/pages/Settings.tsx`
- `frontend/src/scheduling/EditDialog.tsx`
- `frontend/src/scheduling/api.ts`
- `frontend/src/scheduling/board.test.ts`
- `frontend/src/scheduling/board.ts`
- `frontend/src/scheduling/dispatch.css`

## Verification Results
6/6 verification commands passed (run by Triad after the agent finished).

## Verification Commands
| Command | Exit Code | Result |
|---------|-----------|--------|
| `cd frontend && npm run typecheck && npm test && npm run build` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; bash scripts/e2e.sh e2e/dispatch.spec.ts` | 0 | PASS |
| `grep -q 'Application Calendars.ReadWrite' docs/CALENDAR_SETUP.md && grep -q 'CALENDAR_SETUP.md' docs/MAIL_SETUP.md` | 0 | PASS |
| `cd frontend && npx vitest run src/scheduling/board.test.ts && npm run typecheck` | 0 | PASS |
| `cd frontend && npx vitest run src/OutlookSync.test.tsx src/Dispatch.test.tsx && npm run typecheck` | 0 | PASS |
| `grep -q 'Application Calendars.ReadWrite' docs/CALENDAR_SETUP.md && grep -q 'graph_calendar_spike.py' docs/CALENDAR_SETUP.md && grep -q 'CALENDAR_SETUP.md' docs/MAIL_SETUP.md` | 0 | PASS |

## Key Decisions
- `scripts/e2e.sh` is unchanged; the new test needed nothing from it.
- The Settings toggle is shown only when `me.role === "admin"`; everyone else sees on/off text. It reads `enabled` from `GET /calendar-sync/status` and sends `PATCH /settings {outlook_sync_enabled}`, so `frontend/src/api.ts` (not in my file list) is untouched.
- The caption uses the oldest `outlook_fetched_at` among the rows shown. If any shown tech was never fetched, it reads "Outlook busy not loaded yet".
- The shared retry logic is a `useRetrySync` hook in `scheduling/api.ts`. It invalidates every scheduling query, which covers the appointment, the status and the board. On a 409 the edit dialog shows "This sync was already retried; it is no longer failed." and re-reads the appointment.
- The hatch's contrast comes from a solid 3px left rule (#0e7490 on light, #22d3ee on dark) plus the stripes.

## Issues Encountered
- `docs/SCHEDULING.md` and the backend files show as modified in the working tree. They are from earlier waves, not this plan; I did not touch them.
- Escalation #1 from the handoff (the uncommitted `0025_outlook_sync.py` DELETE grant) is still pending. It is outside my scope and I did not touch it.

## Escalations
(none)

## Handoff Context
- **Key outputs**: docs/CALENDAR_SETUP.md; docs/MAIL_SETUP.md; frontend/e2e/dispatch.spec.ts; frontend/src/OutlookSync.test.tsx; frontend/src/pages/Dispatch.tsx; frontend/src/pages/Settings.tsx; frontend/src/scheduling/EditDialog.tsx; frontend/src/scheduling/api.ts; frontend/src/scheduling/board.test.ts; frontend/src/scheduling/board.ts; frontend/src/scheduling/dispatch.css
- **Decisions made**: `scripts/e2e.sh` is unchanged; the new test needed nothing from it.; The Settings toggle is shown only when `me.role === "admin"`; everyone else sees on/off text. It reads `enabled` from `GET /calendar-sync/status` and sends `PATCH /settings {outlook_sync_enabled}`, so `frontend/src/api.ts` (not in my file list) is untouched.; The caption uses the oldest `outlook_fetched_at` among the rows shown. If any shown tech was never fetched, it reads "Outlook busy not loaded yet".; The shared retry logic is a `useRetrySync` hook in `scheduling/api.ts`. It invalidates every scheduling query, which covers the appointment, the status and the board. On a 409 the edit dialog shows "This sync was already retried; it is no longer failed." and re-reads the appointment.; The hatch's contrast comes from a solid 3px left rule (#0e7490 on light, #22d3ee on dark) plus the stripes.
- **Open questions**: (none)
- **Conventions established**: Frontend contract: `Appointment.sync` is read defensively (`sync?.state`) and `outlook_busy` is read as `?? []`, so older fixtures and mocks still work.; `OutlookSyncCard` is exported from `pages/Settings.tsx`; the board and the card share the `schedulingKeys.syncStatus()` query.; `docs/CALENDAR_SETUP.md` is the owner's guide for the Exchange scope (the `PSA Techs` group and the `Application Calendars.ReadWrite` assignment) and for running the spike script.

## Requirements Covered
- REQ-04

## Token Usage
20 requests, 1517476 input tokens (1420834 cached), 26498 output tokens, $0.7907
