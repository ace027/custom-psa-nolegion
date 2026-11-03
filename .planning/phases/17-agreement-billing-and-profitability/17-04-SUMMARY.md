# Plan 17-04 Summary: Agreement controls and reports in the UI

## Result
**Status**: Complete
**Wave**: 3
**Agent**: engineering-frontend-developer
**Completed**: 2026-11-03

## Agent Selection Rationale

| Candidate | Semantic | Heuristic | Memory | Total | Source |
|-----------|----------|-----------|--------|-------|--------|
| engineering-frontend-developer | — | 8 | 3.11 | 11.11 | mandatory |
| engineering-senior-developer | — | 16 | 3.02 | 19.02 | heuristic |
| testing-qa-verification-specialist | — | 14 | 3.13 | 17.13 | heuristic |

- **Task type detected**: implementation
- **Confidence**: LOW
- **Adapter**: claude-code
- **Model tier**: sonnet

## Completed Tasks
- [x] Task 1: Ticket and time entry agreement (done)
- [x] Task 2: Agreement settings and reports (done)
- [x] Task 3: Tests (done)

## Files Modified
- `frontend/src/AgreementAttachment.test.tsx`
- `frontend/src/api.ts`
- `frontend/src/pages/TicketDetail.tsx`
- `frontend/src/pages/billing/Agreements.tsx`
- `frontend/src/pages/reports/ProfitabilityReport.tsx`

## Verification Results
5/5 verification commands passed (run by Triad after the agent finished).

## Verification Commands
| Command | Exit Code | Result |
|---------|-----------|--------|
| `cd frontend && npm run -s typecheck` | 0 | PASS |
| `cd frontend && npx vitest run` | 0 | PASS |
| `cd frontend && npm run -s build` | 0 | PASS |
| `cd frontend && npx vitest run src/AgreementAttachment.test.tsx` | 0 | PASS |
| `cd frontend && npm run -s typecheck && npx vitest run && npm run -s build` | 0 | PASS |

## Key Decisions
- The agreement lists come from GET /agreements, which needs billing:read. Without it the ticket and time rows show text only ("Agreement #id" or "No agreement"), never a select.
- A time entry's select offers agreements still in force on its work_date, plus its current one.
- The Fields card shows a plain Agreement block, not a select, when the client has no agreements.

## Issues Encountered
(none)

## Escalations
(none)

## Handoff Context
- **Key outputs**: frontend/src/AgreementAttachment.test.tsx; frontend/src/api.ts; frontend/src/pages/TicketDetail.tsx; frontend/src/pages/billing/Agreements.tsx; frontend/src/pages/reports/ProfitabilityReport.tsx
- **Decisions made**: The agreement lists come from GET /agreements, which needs billing:read. Without it the ticket and time rows show text only ("Agreement #id" or "No agreement"), never a select.; A time entry's select offers agreements still in force on its work_date, plus its current one.; The Fields card shows a plain Agreement block, not a select, when the client has no agreements.
- **Open questions**: (none)
- **Conventions established**: The profitability toggle sends group only when set to agreement; the default request is unchanged.; The 409 text comes straight from the API's error detail; the UI adds no wording of its own.

## Requirements Covered
- Owner test note 8
- Profitability by agreement

## Token Usage
21 requests, 834898 input tokens (778470 cached), 13826 output tokens, $0.4350
