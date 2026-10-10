# Plan 03-01 Summary: Library spike, scheduling API additions and pure board logic

## Result
**Status**: Complete
**Wave**: 1
**Agent**: engineering-senior-developer
**Completed**: 2026-10-10

## Agent Selection Rationale

| Candidate | Semantic | Heuristic | Memory | Total | Source |
|-----------|----------|-----------|--------|-------|--------|
| engineering-senior-developer | — | 32 | 4.5 | 36.5 | heuristic |
| engineering-backend-architect | — | 20 | 4.67 | 24.67 | heuristic |
| testing-qa-verification-specialist | — | 14 | 4.25 | 18.25 | heuristic |

- **Task type detected**: implementation
- **Confidence**: HIGH
- **Adapter**: claude-code
- **Model tier**: sonnet

## Completed Tasks
- [x] Task 1: Spike: install and prove react-big-calendar under React 19 (done)
- [x] Task 2: Backend: list conflicts and pending time off for the board (done)
- [x] Task 3: Typed client, zone conversion and pure board logic (done)

## Files Modified
- `backend/app/routers/scheduling.py`
- `backend/app/scheduling.py`
- `backend/app/scheduling_schemas.py`
- `backend/tests/test_scheduling_api.py`
- `docs/SCHEDULING.md`
- `docs/verify/dispatch-spike.md`
- `frontend/package-lock.json`
- `frontend/package.json`
- `frontend/src/scheduling/Spike.test.tsx`
- `frontend/src/scheduling/api.ts`
- `frontend/src/scheduling/board.test.ts`
- `frontend/src/scheduling/board.ts`
- `frontend/src/scheduling/zone.test.ts`
- `frontend/src/scheduling/zone.ts`

## Verification Results
11/11 verification commands passed (run by Triad after the agent finished).

## Verification Commands
| Command | Exit Code | Result |
|---------|-----------|--------|
| `cd frontend && npm run typecheck && npm test && npm run build` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_scheduling_api.py tests/test_scheduling_schema.py tests/test_availability.py tests/test_zz_api_contract.py` | 0 | PASS |
| `cd backend && ruff check app tests && ruff format --check app tests` | 0 | PASS |
| `cd frontend && node -e "const p=require('./node_modules/react-big-calendar/package.json'); if(p.license!=='MIT'){console.error(p.license);process.exit(1)}"` | 0 | PASS |
| `cd frontend && test ! -f .npmrc && node -e "if(require('./package.json').overrides)process.exit(1)"` | 0 | PASS |
| `cd frontend && npm ls react-big-calendar date-fns @date-fns/tz >/dev/null` | 0 | PASS |
| `cd frontend && npx vitest run src/scheduling/Spike.test.tsx` | 0 | PASS |
| `grep -qx 'Result: GO' docs/verify/dispatch-spike.md` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_scheduling_api.py tests/test_zz_api_contract.py` | 0 | PASS |
| `cd frontend && npx vitest run src/scheduling` | 0 | PASS |
| `cd frontend && npm run typecheck` | 0 | PASS |

## Key Decisions
- backgroundBlocks takes a third argument, the visible range `{from, to}`. The plan's signature had none, but off-hours is the complement of the working windows within a range.
- moveSummary takes a fourth argument, `zone`, to format "Tue 14:00".
- undoPatch always sends all three of tech_id, starts_at and ends_at from `before`. The `after` parameter is unused, so it is named `_after`.
- dropPatch compares instants rather than strings, so a server value like `+00:00` does not count as a change.
- listStaff returns only {id, display_name, role}.
- The types in this react-big-calendar version reject string accessors, so Spike.test.tsx passes function accessors for resourceIdAccessor and resourceTitleAccessor instead of 'id' and 'title'.

## Issues Encountered
- A wall-clock hour that repeats when clocks fall back maps back to its first occurrence in fromBoardDate. This is documented in zone.ts and tested.
- `npm install` printed EBADENGINE warnings (node 22.22.0 vs the required ^22.22.2) and reported 1 high-severity vulnerability. I did not look into either.
- `.planning/STATE.md` and `.planning/memory/PREFERENCES.md` were already modified before I started; I did not touch them.

## Escalations
(none)

## Handoff Context
- **Key outputs**: backend/app/routers/scheduling.py; backend/app/scheduling.py; backend/app/scheduling_schemas.py; backend/tests/test_scheduling_api.py; docs/SCHEDULING.md; docs/verify/dispatch-spike.md; frontend/package-lock.json; frontend/package.json; frontend/src/scheduling/Spike.test.tsx; frontend/src/scheduling/api.ts; frontend/src/scheduling/board.test.ts; frontend/src/scheduling/board.ts; frontend/src/scheduling/zone.test.ts; frontend/src/scheduling/zone.ts
- **Decisions made**: backgroundBlocks takes a third argument, the visible range `{from, to}`. The plan's signature had none, but off-hours is the complement of the working windows within a range.; moveSummary takes a fourth argument, `zone`, to format "Tue 14:00".; undoPatch always sends all three of tech_id, starts_at and ends_at from `before`. The `after` parameter is unused, so it is named `_after`.; dropPatch compares instants rather than strings, so a server value like `+00:00` does not count as a change.; listStaff returns only {id, display_name, role}.; The types in this react-big-calendar version reject string accessors, so Spike.test.tsx passes function accessors for resourceIdAccessor and resourceTitleAccessor instead of 'id' and 'title'.
- **Open questions**: (none)
- **Conventions established**: Import `schedulingKeys` and the fetchers from `frontend/src/scheduling/api.ts`. Pass `withConflicts: true` to `listAppointments` for the board, with a range of at most 8 days.; Board dates are fake-local. Convert with `toBoardDate`/`fromBoardDate` and the org zone (`getOrgTimezone`). Get ranges from `zoneDayRange`/`zoneWeekRange`.; Call `moveSummary(before, after, staff, zone)`, `backgroundBlocks(rows, zone, {from, to})`, and `dropPatch(a, {start, end, resourceId}, zone)`.; 03-02 must lazy-load react-big-calendar and fill in the gzip size in docs/verify/dispatch-spike.md. It also needs to import the library CSS, because the tests do not.; `BoardEvent`, `BackgroundBlock` and `CONFLICT_LABEL` are exported from board.ts.

## Requirements Covered
- REQ-03

## Token Usage
13 requests, 761635 input tokens (680712 cached), 25146 output tokens, $0.5899
