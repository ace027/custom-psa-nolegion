# Project State

## Current Position
- **Phase**: 6 of 13 (planned)
- **Status**: Phase 6 planned -- 3 plans across 3 waves
- **Last Activity**: Phase 6 planning (2026-10-19)

## Progress
```
[########............] 40% — 18/44 plans complete
```

## Recent Decisions
- Block-hour unused hours expire at month end (no rollover)
- Keep one tax rate per client
- No payment processor; portal payments stay manual
- No data import from another PSA
- Scheduling follows approach B from .planning/explorations/2026-10-09-scheduling-dispatch-design.md
- Scheduling supports per-tech timezones
- Calendar board uses an MIT library (react-big-calendar after a spike)
- Appointments link to tickets only (no SLA or billing effect)
- Owner manual testing deferred to a final Phase 14: Verify (.planning/VERIFY.md)

## Next Action
Run `/triad:build` to execute Phase 6: RMM alerts to tickets

## Phase 1 Results
(build started 2026-10-09)
- Plan 01-01 (Wave 1): Block agreement schema, validation and money rules — Complete

## GitHub
- Phase 1 issue: #2 (closed)
- Phase 2 issue: #3 (closed); shipped in PR #4
- Phase 3 issue: #5 (closed); merged to main in PR #4
- Phase 4 issue: #6 (closed); merged to main in PR #7
- Phase 5 issue: #8 (closed); merged to main in PR #9
- Phase 6 issue: #10 (open)

## Phase 2 Results
(build started 2026-10-09)
- Plan 02-01 (Wave 1): Scheduling schema, RLS and permissions — Complete
- Plan 02-02 (Wave 1): Pure availability math — Complete

## Phase 3 Results
(build started 2026-10-10)
- Plan 03-01 (Wave 1): Library spike, scheduling API additions and pure board logic — Complete
- Plan 03-02 (Wave 2): Dispatch board page — Complete with Warnings
- Plan 03-03 (Wave 3): Appointments on the ticket, timer start, and the Playwright booking flow — FAILED: Verification failed: service postgresql start >/dev/null 2>&1; bash scripts/e2e.sh e2e/dispatch.spec.ts; service postgresql start >/dev/null 2>&1; bash scripts/e2e.sh e2e/dispatch.spec.ts --repeat-eac
- Plan 03-03 (Wave 3): Appointments on the ticket, timer start, and the Playwright booking flow — PARTIAL: All three tasks are on disk and every verification command passes. One caveat: `frontend/src/pages/Dispatch.tsx` is modified, and it is on the forbidden list. The edit was already in the tree when I s
- Plan 03-03 (Wave 3): Appointments on the ticket, timer start, and the Playwright booking flow — PARTIAL: All three tasks are in place and the verification commands pass. One problem: `frontend/src/pages/Dispatch.tsx` has an edit in the working tree, and that file is on the must-not-touch list.
- Plan 03-03 (Wave 3): Appointments on the ticket, timer start, and the Playwright booking flow — Complete

## Quick Tasks
- 2026-10-10: date tests use the business timezone (fixes PR #4 CI failing between 00:00 and 05:00 UTC), f69cd2f

## Phase 4 Results
(build started 2026-10-10)
- Plan 04-01 (Wave 1): Graph calendar client, fake Graph calendar endpoints and the tenant spike script — Complete
- Plan 04-02 (Wave 2): Sync schema, outbox enqueue and the worker push job — Complete
- Plan 04-03 (Wave 3): Free/busy cache job and the sync status, retry and availability API — BLOCKED: Needs a new migration in backend/alembic/ (forbidden) to grant DELETE on busy_blocks to psa_app.
- Plan 04-03 (Wave 3): Free/busy cache job and the sync status, retry and availability API — PARTIAL: All three tasks are on disk and the plan's checks pass: 65 passed, 1 skipped, and ruff is clean. One caveat is the `GRANT ... DELETE` edit to forbidden `0025_outlook_sync.py`. It is described under is
- Plan 04-03 (Wave 3): Free/busy cache job and the sync status, retry and availability API — Complete with Warnings
- Plan 04-04 (Wave 4): Board Outlook busy shading, sync badges, settings card and setup docs — Complete
- 2026-10-15: owner manual testing moved to a final Phase 14: Verify; deferred checks queued in .planning/VERIFY.md

## Phase 5 Results
(build started 2026-10-15)
- Plan 05-01 (Wave 1): Schema, models, schemas and on-call math — PARTIAL: Migration 0026, models, schemas, `app/oncall.py` and both test files are on disk. Ruff check, format and the schema import pass. The 21 new tests and the alembic round-trip passed in an earlier run be
- Plan 05-01 (Wave 1): Schema, models, schemas and on-call math — Complete
- Plan 05-02 (Wave 2): Client appointment emails — Complete
- Plan 05-03 (Wave 2): On-call API and portal appointments — BLOCKED: The plan does not say how a rotation gets its organization_id. I will not guess a source for it, because the choice shapes the RLS behavior and the API contract that plan 05-04 will build on.
- Plan 05-03 (Wave 2): On-call API and portal appointments — Complete
- Plan 05-04 (Wave 3): Staff UI: email switch, on-call page, widget and board — Complete
- Plan 05-05 (Wave 3): Portal appointments page, docs and verify checklist — PARTIAL: Portal Appointments page, tests, docs and the Phase 5 verify checklist are done. The full vitest run has 1 failure in Dispatch.test.tsx, caused by 05-04's in-flight work, not these files. typecheck an
- Plan 05-05 (Wave 3): Portal appointments page, docs and verify checklist — Complete
