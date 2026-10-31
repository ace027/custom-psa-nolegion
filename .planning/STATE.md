# Project State

## Current Position
- **Phase**: 12 of 13 (executed, pending review)
- **Status**: Phase 12 complete — all plans executed successfully
- **Last Activity**: Plan 12-04 execution (2026-10-31)

## Progress
```
[#################...] 87% — 42/48 plans complete
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
- Owner manual testing deferred to a final Phase 15: Verify (.planning/VERIFY.md)
- Integration readiness inserted as Phase 12 before release; knowledge base, portal polish and verify renumbered 13-15
- Ticket sources: manual, email, portal, rmm, api, rule (ui renamed to manual)
- API moves to /api/v1 with no /api alias; owner updates the Entra redirect URI
- Automation time is reported as its own column, outside utilisation % and labour cost

## Next Action
Run `/triad:review` to verify Phase 12: Integration readiness

## Phase 1 Results
(build started 2026-10-09)
- Plan 01-01 (Wave 1): Block agreement schema, validation and money rules — Complete

## GitHub
- Phase 1 issue: #2 (closed)
- Phase 2 issue: #3 (closed); shipped in PR #4
- Phase 3 issue: #5 (closed); merged to main in PR #4
- Phase 4 issue: #6 (closed); merged to main in PR #7
- Phase 5 issue: #8 (closed); merged to main in PR #9
- Phase 6 issue: #10 (closes with PR #11); PR #11 dev -> main
- Phase 7 issue: #12
- Phase 8 issue: #13
- Phase 9 issue: #14
- Phase 12 issue: #17

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
- 2026-10-20: phase 6 low and info security items: NinjaOne host allowlist, credentials re-entered on host change, inactive or archived clients skipped
- 2026-10-24: Node.js October 2026 security releases: frontend build requires patched Node 22.23.4 (Dockerfile, CI via .nvmrc, engines), c24004a; npm audit fix for dev-only vite, vitest, undici and source-map-js advisories
- 2026-10-29: report schedules form no longer loses unsaved input (other Edit buttons and New schedule are disabled while a form is open; focus moves into the form and back to its opener)

## Phase 4 Results
(build started 2026-10-10)
- Plan 04-01 (Wave 1): Graph calendar client, fake Graph calendar endpoints and the tenant spike script — Complete
- Plan 04-02 (Wave 2): Sync schema, outbox enqueue and the worker push job — Complete
- Plan 04-03 (Wave 3): Free/busy cache job and the sync status, retry and availability API — BLOCKED: Needs a new migration in backend/alembic/ (forbidden) to grant DELETE on busy_blocks to psa_app.
- Plan 04-03 (Wave 3): Free/busy cache job and the sync status, retry and availability API — PARTIAL: All three tasks are on disk and the plan's checks pass: 65 passed, 1 skipped, and ruff is clean. One caveat is the `GRANT ... DELETE` edit to forbidden `0025_outlook_sync.py`. It is described under is
- Plan 04-03 (Wave 3): Free/busy cache job and the sync status, retry and availability API — Complete with Warnings
- Plan 04-04 (Wave 4): Board Outlook busy shading, sync badges, settings card and setup docs — Complete
- 2026-10-15: owner manual testing moved to a final Phase 15: Verify; deferred checks queued in .planning/VERIFY.md

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

## Phase 6 Results
(build started 2026-10-20)
- Plan 06-01 (Wave 1): RMM alert schema, models and NinjaOne alert adapter — Complete
- Plan 06-02 (Wave 2): Alert polling engine, worker job and admin API — Complete
- Plan 06-03 (Wave 3): Integrations alerts panel, ticket device chip and verify docs — Complete

## Phase 7 Results
(build started 2026-10-21)
- Plan 07-01 (Wave 1): Automation & API schema, models and permissions — Complete
- Plan 07-02 (Wave 2): API keys: hashed, scoped, revocable bearer auth — Complete
- Plan 07-03 (Wave 3): Events and signed outbound webhooks (generic, Teams, n8n) — Complete
- Plan 07-04 (Wave 4): Rules engine with dry run, trace and loop guard — PARTIAL: Rules engine, routes, rule builder page, docs and the Phase 7 checklist are done and their tests pass. The full backend suite was not re-run in one go after a late fix. A first full run stopped at tes
- Plan 07-04 (Wave 4): Rules engine with dry run, trace and loop guard — Complete

## Phase 8 Results
(build started 2026-10-21)
- Plan 08-01 (Wave 1): Projects schema, permissions and approved money rules — Complete
- Plan 08-02 (Wave 2): Projects, phases, tasks, dependencies and budget vs actual API — Complete
- Plan 08-03 (Wave 3): Project billing: fixed fee up front and capped T&M — PARTIAL: Project billing is on disk: fixed fee up front, fee-covered time on a $0 line, the T&M budget cap, bill-fixed-fee, voiding releases the fee, and project time is kept out of normal billing and block ho
- Plan 08-04 (Wave 3): Projects UI: list, detail, board view, budget card, seed and verify checklist — PARTIAL: The UI, tests, seed data and checklist are done. Typecheck, the full vitest run (259 tests), build and ruff all pass. tests/test_seed_and_migrations.py now fails, and I couldn't update it because it i
- Plan 08-03 (Wave 3): Project billing: fixed fee up front and capped T&M — Complete with Warnings
- Plan 08-04 (Wave 3): Projects UI: list, detail, board view, budget card, seed and verify checklist — Complete

## Phase 9 Results
(build started 2026-10-21)
- Plan 09-01 (Wave 1): CRM schema, stages and permissions — Complete
- Plan 09-02 (Wave 2): CRM service, quote link, forecast and renewal job — PARTIAL: CRM service, quote accept hook, forecast, renewal scan, worker job, settings fields and all routes are implemented and tested. Ruff passes. The plan's verification pytest set passed (125). A full-suit
- Plan 09-02 (Wave 2): CRM service, quote link, forecast and renewal job — Complete
- Plan 09-03 (Wave 3): Sales pipeline, forecast and renewals UI, docs and verify checklist — Complete

## Phase 10 Results
(build started 2026-10-29)
- Plan 10-01 (Wave 1): Procurement schema, models and permissions — Complete
- Plan 10-02 (Wave 2): Procurement service and API: vendors, POs, receiving, inventory, delivery billing, markup — BLOCKED: The plan requires DELETE routes for PO lines and markup rules, but psa_app has no DELETE grant on those tables (alembic/versions/0031_procurement.py line 171). The fix needs a migration, or a change t
- Plan 10-02 (Wave 2): Procurement service and API: vendors, POs, receiving, inventory, delivery billing, markup — Complete
- Plan 10-03 (Wave 3): Procurement UI, client inventory card and docs — Complete with Warnings

## Phase 11 Results
(build started 2026-10-29)
- Plan 11-01 (Wave 1): Report metrics: SLA, utilisation, aging, profitability with CSV — Complete
- Plan 11-02 (Wave 2): Role dashboards API and scheduled report emails — Complete
- Plan 11-03 (Wave 3): Report pages, role dashboards UI, cost rates and docs — Complete

## Phase 12 Results
(build started 2026-10-31)
- Plan 12-01 (Wave 1): Integration-readiness schema, models, schemas and writers — PARTIAL: Migration 0033, models, schemas, writers, tests and docs are done. Ruff is clean and the 10 verification test files pass (176 passed, 1 skipped). I did not get a clean full-suite run (see issues). A `
- Plan 12-01 (Wave 1): Integration-readiness schema, models, schemas and writers — Complete
- Plan 12-02 (Wave 2): Automation time kept out of billing; reported separately — Complete
- Plan 12-03 (Wave 2): Frontend: branding config, client scope module, note authors and new fields — Complete
- Plan 12-04 (Wave 3): /api/v1 everywhere and the committed OpenAPI spec — Complete
