# Plan 05-05 Summary: Portal appointments page, docs and verify checklist

## Result
**Status**: Partial
**Wave**: 3
**Agent**: engineering-frontend-developer
**Completed**: 2026-10-15

## Agent Selection Rationale

| Candidate | Semantic | Heuristic | Memory | Total | Source |
|-----------|----------|-----------|--------|-------|--------|
| engineering-frontend-developer | — | 7 | 4.2 | 11.2 | mandatory |
| engineering-senior-developer | — | 16 | 3.65 | 19.65 | heuristic |
| testing-qa-verification-specialist | — | 12 | 4.38 | 16.38 | heuristic |

- **Task type detected**: implementation
- **Confidence**: LOW
- **Adapter**: claude-code
- **Model tier**: sonnet

## Completed Tasks
- [x] Task 1: Portal Appointments page (done)
- [x] Task 2: Tests (done)
- [x] Task 3: Docs and verify checklist (done)

## Files Modified
- `docs/PORTAL.md`
- `docs/SCHEDULING.md`
- `docs/verify/client-notices-oncall.md`
- `frontend/src/PortalAppointments.test.tsx`
- `frontend/src/portal/AppointmentsPage.tsx`
- `frontend/src/portal/PortalApp.tsx`
- `frontend/src/portal/appointments.ts`

## Verification Results
4/4 verification commands passed (run by Triad after the agent finished).

## Verification Commands
| Command | Exit Code | Result |
|---------|-----------|--------|
| `cd frontend && npm run typecheck && npx vitest run && npm run build` | 0 | PASS |
| `test -f docs/verify/client-notices-oncall.md && grep -q 'Phase 5' .planning/VERIFY.md` | 0 | PASS |
| `cd frontend && npm run typecheck` | 0 | PASS |
| `cd frontend && npx vitest run src/PortalAppointments.test.tsx` | 0 | PASS |

## Key Decisions
- The Appointments tab is always shown, because PortalMe has no flag for it. The visibility rule is enforced server-side.
- An appointment counts as upcoming while its ends_at is still in the future. Upcoming sorts soonest first, past sorts most recent first.
- I put the PortalAppointment type in appointments.ts, because api.ts is outside my file list.

## Issues Encountered
- The Dispatch.test.tsx failure: the POST body now has an extra field (notify_client) from 05-04's BookingDialog change. 05-04 owns that test and file; once it updates the expected body the full suite should be green. I did not touch it.

## Escalations
(none)

## Handoff Context
- **Key outputs**: docs/PORTAL.md; docs/SCHEDULING.md; docs/verify/client-notices-oncall.md; frontend/src/PortalAppointments.test.tsx; frontend/src/portal/AppointmentsPage.tsx; frontend/src/portal/PortalApp.tsx; frontend/src/portal/appointments.ts
- **Decisions made**: The Appointments tab is always shown, because PortalMe has no flag for it. The visibility rule is enforced server-side.; An appointment counts as upcoming while its ends_at is still in the future. Upcoming sorts soonest first, past sorts most recent first.; I put the PortalAppointment type in appointments.ts, because api.ts is outside my file list.
- **Open questions**: (none)
- **Conventions established**: Portal route is /portal/appointments, query key ["portal","appointments"], backed by GET /api/portal/appointments.; The full-suite check needs to be re-run after 05-04 lands.

## Requirements Covered
- REQ-05

## Token Usage
7 requests, 278603 input tokens (228451 cached), 8798 output tokens, $0.2590
