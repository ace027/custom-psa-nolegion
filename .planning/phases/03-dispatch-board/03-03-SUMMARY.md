# Plan 03-03 Summary: Appointments on the ticket, timer start, and the Playwright booking flow

## Result
**Status**: Failed
**Wave**: 3
**Agent**: engineering-senior-developer
**Completed**: 2026-10-10
**Failure Class**: BLOCKER — $ service postgresql start >/dev/null 2>&1; bash scripts/e2e.sh e2e/dispatch.spec.ts (exit 1)

## Agent Selection Rationale

| Candidate | Semantic | Heuristic | Memory | Total | Source |
|-----------|----------|-----------|--------|-------|--------|
| engineering-senior-developer | — | 23 | 4.5 | 27.5 | heuristic |
| engineering-backend-architect | — | 22 | 4.67 | 26.67 | heuristic |
| testing-qa-verification-specialist | — | 18 | 4.25 | 22.25 | heuristic |

- **Task type detected**: implementation
- **Confidence**: MEDIUM
- **Adapter**: claude-code
- **Model tier**: sonnet

## Completed Tasks
- [x] Task 1: Ticket appointments card with Book and Start timer (done)
- [x] Task 2: Isolated local e2e runner (done)
- [x] Task 3: Playwright booking flow (done)

## Files Modified
- `docs/DEVELOPMENT.md`
- `docs/verify/dispatch-board.md`
- `frontend/e2e/dispatch.spec.ts`
- `frontend/playwright.config.ts`
- `frontend/src/TicketAppointments.test.tsx`
- `frontend/src/pages/TicketAppointmentsCard.tsx`
- `frontend/src/pages/TicketDetail.tsx`
- `frontend/vite.config.ts`
- `scripts/e2e.sh`

## Verification Results
4/6 verification commands passed (run by Triad after the agent finished).

## Verification Commands
| Command | Exit Code | Result |
|---------|-----------|--------|
| `cd frontend && npm run typecheck && npm test && npm run build` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; bash scripts/e2e.sh e2e/dispatch.spec.ts` | 1 | FAIL |
| `cd frontend && npx vitest run src/TicketAppointments.test.tsx && npm run typecheck` | 0 | PASS |
| `bash -n scripts/e2e.sh && test -x scripts/e2e.sh` | 0 | PASS |
| `cd frontend && npm run typecheck` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; bash scripts/e2e.sh e2e/dispatch.spec.ts --repeat-each=3` | 1 | FAIL |

## Key Decisions
- Without ticket_id-only params the TS type requires from/to, and api.ts is forbidden. The card casts `{ticketId} as AppointmentListParams`; the backend accepts ticket_id alone.
- The Work type default on the card is blank ("Select…"), same as TimeCard; Start is disabled until one is chosen. It reuses useLookups().workTypes and invalidates ["timer"], the key TimerBar uses.
- The board link date is the appointment's day in the org zone.
- The runner's health path is /healthz, with no /api prefix.

## Issues Encountered
- Pre-existing: e2e/smoke.spec.ts "ticket lifecycle" fails at line 50. It expects the Status select value "resolved" but gets the id "4". This is not caused by my change, and the file is outside my list.
- In this sandbox Playwright wants chromium_headless_shell-1243, but /opt/pw-browsers only has 1194. CHROMIUM_PATH=/opt/pw-browsers/chromium-1194/chrome-linux/chrome is required here, so the plan's "leave it unset" does not work in this environment.
- .planning/memory/PREFERENCES.md shows as modified in git; I did not touch it.
- I briefly ran `git stash` by mistake and popped it straight away; all changes are intact.
- BLOCKER: $ service postgresql start >/dev/null 2>&1; bash scripts/e2e.sh e2e/dispatch.spec.ts (exit 1)

## Escalations
| # | Severity | Type | Decision | Status | Resolution |
|---|----------|------|----------|--------|------------|
| 1 | warning | scope / reliability | Fix `withDragAndDrop` interop in frontend/src/pages/Dispatch.tsx, then remove the dnd-default-interop plugin and the optimizeDeps.include entry from vite.config.ts. | pending | INVALID: type "scope / reliability" is not one of architecture, dependency, scope, schema, api, deletion, infrastructure, quality |
| 2 | warning | scope | frontend/e2e/dispatch.spec.ts (tests) is outside the directory mappings for tests (backend/tests); suggested location: backend/tests/dispatch.spec.ts | pending |  |
| 3 | blocker | api | Resolve: $ service postgresql start >/dev/null 2>&1; bash scripts/e2e.sh e2e/dispatch.spec.ts (exit 1) | pending |  |

- #1 context: The dev server (vite 8) passes the `react-big-calendar/lib/addons/dragAndDrop` default import as the whole CJS exports object. Dispatch.tsx then throws "withDragAndDrop is not a function" and the board renders blank in `npm run dev`. Vitest and the production build are unaffected. It was hidden on a cold optimizer cache, so my first e2e run passed once and later runs failed. Dispatch.tsx and frontend/src/scheduling/ are forbidden to me, so I worked around it in vite.config.ts, which is in my file list. The proper fix is `const dnd = (m as any).default ?? m` style unwrapping in Dispatch.tsx.
- #3 context: Verification failed (service postgresql start >/dev/null 2>&1; bash scripts/e2e.sh e2e/dispatch.spec.ts; service postgresql start >/dev/null 2>&1; bash scripts/e2e.sh e2e/dispatch.spec.ts --repeat-each=3); a BLOCKER is not auto-fixed.

## Handoff Context
- **Key outputs**: docs/DEVELOPMENT.md; docs/verify/dispatch-board.md; frontend/e2e/dispatch.spec.ts; frontend/playwright.config.ts; frontend/src/TicketAppointments.test.tsx; frontend/src/pages/TicketAppointmentsCard.tsx; frontend/src/pages/TicketDetail.tsx; frontend/vite.config.ts; scripts/e2e.sh
- **Decisions made**: Without ticket_id-only params the TS type requires from/to, and api.ts is forbidden. The card casts `{ticketId} as AppointmentListParams`; the backend accepts ticket_id alone.; The Work type default on the card is blank ("Select…"), same as TimeCard; Start is disabled until one is chosen. It reuses useLookups().workTypes and invalidates ["timer"], the key TimerBar uses.; The board link date is the appointment's day in the org zone.; The runner's health path is /healthz, with no /api prefix.
- **Open questions**: (none)
- **Conventions established**: Run e2e with `bash scripts/e2e.sh <spec> [args]`; set CHROMIUM_PATH if the bundled browser is missing.; Dispatch.tsx has a latent bug under the Vite dev server; the vite.config.ts shim covers it until Dispatch.tsx is fixed.; Playwright dialog queries are scoped to getByRole('dialog'), and the ticket page now has two 'Work type' labels when the card's timer form is open.

## Requirements Covered
- REQ-03

## Error Details
Verification failed: service postgresql start >/dev/null 2>&1; bash scripts/e2e.sh e2e/dispatch.spec.ts; service postgresql start >/dev/null 2>&1; bash scripts/e2e.sh e2e/dispatch.spec.ts --repeat-each=3

### Failed verification output
`service postgresql start >/dev/null 2>&1; bash scripts/e2e.sh e2e/dispatch.spec.ts`
```
           ║
    ╚════════════════════════════════════════════════════════════╝

    Error Context: test-results/dispatch-reassigning-onto-a-busy-tech-shows-the-conflict/error-context.md

  3) e2e/dispatch.spec.ts:157:1 › drag an event one hour later ─────────────────────────────────────

    Error: browserType.launch: Executable doesn't exist at /opt/pw-browsers/chromium_headless_shell-1243/chrome-headless-shell-linux64/chrome-headless-shell
    ╔════════════════════════════════════════════════════════════╗
    ║ Looks like Playwright was just installed or updated.       ║
    ║ Please run the following command to download new browsers: ║
    ║                                                            ║
    ║     npx playwright install                                 ║
    ║                                                            ║
    ║ <3 Playwright Team                                         ║
    ╚════════════════════════════════════════════════════════════╝

    Error Context: test-results/dispatch-drag-an-event-one-hour-later/error-context.md

  3 failed
    e2e/dispatch.spec.ts:78:1 › book from the ticket, see it on the board, edit it, undo ───────────
    e2e/dispatch.spec.ts:134:1 › reassigning onto a busy tech shows the conflict ───────────────────
    e2e/dispatch.spec.ts:157:1 › drag an event one hour later ──────────────────────────────────────
e2e: failed (exit 1). Logs: /tmp/psa-e2e.odNXCh/api.log /tmp/psa-e2e.odNXCh/web.log /tmp/psa-e2e.odNXCh/setup.log

```
`service postgresql start >/dev/null 2>&1; bash scripts/e2e.sh e2e/dispatch.spec.ts --repeat-each=3`
```
mmand to download new browsers: ║
    ║                                                            ║
    ║     npx playwright install                                 ║
    ║                                                            ║
    ║ <3 Playwright Team                                         ║
    ╚════════════════════════════════════════════════════════════╝

    Error Context: test-results/dispatch-drag-an-event-one-hour-later-repeat2/error-context.md

  9 failed
    e2e/dispatch.spec.ts:78:1 › book from the ticket, see it on the board, edit it, undo ───────────
    e2e/dispatch.spec.ts:134:1 › reassigning onto a busy tech shows the conflict ───────────────────
    e2e/dispatch.spec.ts:157:1 › drag an event one hour later ──────────────────────────────────────
    e2e/dispatch.spec.ts:78:1 › book from the ticket, see it on the board, edit it, undo ───────────
    e2e/dispatch.spec.ts:134:1 › reassigning onto a busy tech shows the conflict ───────────────────
    e2e/dispatch.spec.ts:157:1 › drag an event one hour later ──────────────────────────────────────
    e2e/dispatch.spec.ts:78:1 › book from the ticket, see it on the board, edit it, undo ───────────
    e2e/dispatch.spec.ts:134:1 › reassigning onto a busy tech shows the conflict ───────────────────
    e2e/dispatch.spec.ts:157:1 › drag an event one hour later ──────────────────────────────────────
e2e: failed (exit 1). Logs: /tmp/psa-e2e.9iAsd2/api.log /tmp/psa-e2e.9iAsd2/web.log /tmp/psa-e2e.9iAsd2/setup.log

```

## Token Usage
46 requests, 4004978 input tokens (3886329 cached), 39810 output tokens, $1.4719
