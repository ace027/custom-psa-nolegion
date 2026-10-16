# Plan 05-04 Summary: Staff UI: email switch, on-call page, widget and board

## Result
**Status**: Complete
**Wave**: 3
**Agent**: engineering-frontend-developer
**Completed**: 2026-10-15

## Agent Selection Rationale

| Candidate | Semantic | Heuristic | Memory | Total | Source |
|-----------|----------|-----------|--------|-------|--------|
| engineering-frontend-developer | — | 7 | 4.2 | 11.2 | mandatory |
| engineering-senior-developer | — | 14 | 3.65 | 17.65 | heuristic |
| testing-qa-verification-specialist | — | 13 | 4.38 | 17.38 | heuristic |

- **Task type detected**: implementation
- **Confidence**: LOW
- **Adapter**: claude-code
- **Model tier**: sonnet

## Completed Tasks
- [x] Task 1: Email switch and booking checkbox (done)
- [x] Task 2: On-call page and widget (done)
- [x] Task 3: Board shading and tests (done)

## Files Modified
- `frontend/src/App.tsx`
- `frontend/src/OnCall.test.tsx`
- `frontend/src/OnCallWidget.tsx`
- `frontend/src/pages/Dispatch.tsx`
- `frontend/src/pages/OnCall.tsx`
- `frontend/src/pages/Settings.tsx`
- `frontend/src/scheduling/BookingDialog.tsx`
- `frontend/src/scheduling/EditDialog.tsx`
- `frontend/src/scheduling/api.ts`
- `frontend/src/scheduling/board.test.ts`
- `frontend/src/scheduling/board.ts`
- `frontend/src/scheduling/dispatch.css`
- `frontend/src/scheduling/oncall.ts`

## Verification Results
3/3 verification commands passed (run by Triad after the agent finished).

## Verification Commands
| Command | Exit Code | Result |
|---------|-----------|--------|
| `cd frontend && npm run typecheck && npx vitest run && npm run build` | 0 | PASS |
| `cd frontend && npm run typecheck` | 0 | PASS |
| `cd frontend && npx vitest run src/OnCall.test.tsx src/scheduling/board.test.ts` | 0 | PASS |

## Key Decisions
- The booking payload omits notify_client unless the box is ticked, so it sends `notify_client: false` or nothing. The server default is true, and always sending it broke an existing assertion in src/Dispatch.test.tsx, which is outside my file list.
- frontend/src/api.ts (forbidden) has no appointment_emails_enabled in AppSettings, so the Settings card widens the type locally.
- A shift's rotation name comes from a separate /oncall/rotations query, because ShiftOut carries no rotation name.
- If the on-call queries fail, the board just shows no bands. They are not added to the board's load error.
- Changing the handoff weekday moves the anchor date to the next date on that weekday. Overrides are entered in the business timezone.
- Editing a rotation sends the full patch, including member_ids and active.

## Issues Encountered
(none)

## Escalations
(none)

## Handoff Context
- **Key outputs**: frontend/src/App.tsx; frontend/src/OnCall.test.tsx; frontend/src/OnCallWidget.tsx; frontend/src/pages/Dispatch.tsx; frontend/src/pages/OnCall.tsx; frontend/src/pages/Settings.tsx; frontend/src/scheduling/BookingDialog.tsx; frontend/src/scheduling/EditDialog.tsx; frontend/src/scheduling/api.ts; frontend/src/scheduling/board.test.ts; frontend/src/scheduling/board.ts; frontend/src/scheduling/dispatch.css; frontend/src/scheduling/oncall.ts
- **Decisions made**: The booking payload omits notify_client unless the box is ticked, so it sends `notify_client: false` or nothing. The server default is true, and always sending it broke an existing assertion in src/Dispatch.test.tsx, which is outside my file list.; frontend/src/api.ts (forbidden) has no appointment_emails_enabled in AppSettings, so the Settings card widens the type locally.; A shift's rotation name comes from a separate /oncall/rotations query, because ShiftOut carries no rotation name.; If the on-call queries fail, the board just shows no bands. They are not added to the board's load error.; Changing the handoff weekday moves the anchor date to the next date on that weekday. Overrides are entered in the business timezone.; Editing a rotation sends the full patch, including member_ids and active.
- **Open questions**: (none)
- **Conventions established**: Routes used: GET/POST /api/oncall/rotations, PATCH /api/oncall/rotations/{id}, GET/POST /api/oncall/rotations/{id}/overrides, DELETE /api/oncall/overrides/{id}, GET /api/oncall/now, GET /api/oncall/schedule?start&end.; `backgroundBlocks(availability, zone, range, shifts?, rotationNames?)` is backward compatible.; AppSettings in frontend/src/api.ts could gain appointment_emails_enabled in a later plan.; 05-04-SUMMARY.md is left for Triad to write.

## Requirements Covered
- REQ-05

## Token Usage
18 requests, 1351650 input tokens (1252254 cached), 25020 output tokens, $0.7491
