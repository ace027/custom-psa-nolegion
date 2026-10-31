# Phase 12: Integration readiness — Review Summary

## Result: PASSED

**Cycles Used**: 1
**Reviewers**: testing-qa-verification-specialist, testing-api-tester, engineering-backend-architect, design-ux-researcher
**Evaluators**: code-quality, ui-ux, integration, business-logic
**Completed**: 2026-10-31

## Findings Summary
- Must-fix (blocker, critical, major) found: 0; fixed: 0; unresolved: 0
- Suggestions (minor, advisory): 1
- Deferred (confidence 50-79%): 10
- Hot spots (flagged by 2+ reviewers): `frontend/src/pages/TicketDetail.tsx`, `backend/app/ticket_links.py`

## Findings Detail
| ID | Severity | Location | Issue | Reviewers | Confidence | Status |
|----|----------|----------|-------|-----------|------------|--------|
| F-001 | minor | `backend/app/projects.py:565-572` | `_minutes_by_ticket` sums `minutes_actual` without the `entry_type == "labour"` filter. `budget()` at lines 592-597 does filter on it, so the two figures disagree on a project that has automation entries. | evaluator:business-logic | 80% | deferred |

## Reviewer Verdicts
- Cycle 1, testing-qa-verification-specialist: **PASS**
- Cycle 1, testing-api-tester: **PASS**
- Cycle 1, engineering-backend-architect: **PASS**
- Cycle 1, design-ux-researcher: **PASS**
- Cycle 1, evaluator:code-quality: **PASS**
- Cycle 1, evaluator:ui-ux: **PASS**
- Cycle 1, evaluator:integration: **NEEDS WORK**
- Cycle 1, evaluator:business-logic: **NEEDS WORK**

## Suggestions (Not Required)
- F-001 `backend/app/projects.py`: `_minutes_by_ticket` sums `minutes_actual` without the `entry_type == "labour"` filter. `budget()` at lines 592-597 does filter on it, so the two figures disagree on a project that has automation entries. (fix: Add `TimeEntry.entry_type == "labour"` to the `where` clause in `_minutes_by_ticket`. Add a test with an automation entry on a project ticket.)

## Deferred (Medium Confidence)
- `frontend/src/pages/TicketDetail.tsx` [minor, 60%]: The author filter keeps its value after a note is posted. A new note is always `human`, so if the filter is set to System or AI, the note the user just added doesn't appear. The list shows "No system notes" or the filtered list, with no sign that the post worked.
- `backend/app/ticket_links.py` [major, 65%]: `_pointer_note` sets `author_user_id=ctx.user.id if ctx.user else None` but never sets `author_type`. The column defaults to `human`, so a note with no user and no email (system/automation context) is stored as `human`. `ticket_services.py` lines 363-371 has the same gap: `add_note` uses `ctx.user` conditionally and has no `author_type`. Only the note at line 390 sets `system`.
- `frontend/src/pages/TicketDetail.tsx` [minor, 60%]: `noteTone` gives AI notes `border-violet-100 bg-violet-100`, so the border is the same colour as the fill and no edge shows. The system and AI tones are hard-coded Tailwind palette classes (`slate-100`, `violet-100`), while the other branches use the `bg-surface` token. The same hard-coded `violet-100` and `violet-800` pair is used for the AI badge (line 378) and the Automation badge (line 439).
- `frontend/src/pages/TicketDetail.tsx` [minor, 55%]: The empty-state messages that appear when the author filter hides every note are not in a live region. The filter buttons change the list without announcing the result.
- `frontend/src/clientScope.ts` [advisory, 50%]: `apiPath` and `route` throw "No client in scope" when `orgId` is null, and the exception is raised during render if a component calls them unguarded.
- `frontend/src/pages/billing/Payments.tsx (also billing/CreditMemos.tsx 40 and 82, billing/Invoices.tsx 34, pages/quotes/SurveyPage.tsx 142-144, billing/Payments.tsx 38 and 120)` [major, 60%]: Client-scoped calls are hand-built as `/invoices?organization_id=${orgId}...`, `/quotes?organization_id=...` and `/agreements?organization_id=...`. They bypass `useClientScope`/`clientApiPath`. Some pages do use the hook (OrganizationDetail, OrgBillingCard).
- `backend/app/asset_sync.py` [minor, 50%]: Synced assets get `source` ('rmm' or 'import') but `assets.external_id` is never set. The vendor id is stored only in `AssetSource.external_id`. The migration does not backfill `assets.external_id` either.
- `backend/app/timekeeping.py` [major, 70%]: The weekly timesheet query reads every non-voided `TimeEntry` with no `entry_type` filter. Rows carry no `entry_type`, and the day `minutes` and `billable_minutes` totals add automation minutes to labour minutes.
- `backend/app/ticket_services.py, /home/user/custom-psa-nolegion/backend/app/ticket_links.py` [minor, 60%]: Both note constructors set `author_user_id=ctx.user.id if ctx.user else None` but leave `author_type` at the default `human`. A note written with no user (system actor) gets `human` and has no author. The migration's backfill rule would classify the same note as `system`.
- `backend/alembic/versions/0033_integration_readiness.py, /home/user/custom-psa-nolegion/backend/app/asset_sync.py` [minor, 50%]: The backfill and the sync set `assets.source` but never set `assets.external_id`. Synced assets keep a null `external_id`, so the unique index on `(source, external_id)` is never exercised for the assets that matter.

## Fixes Applied
- minor findings: engineering-backend-architect on F-001, F-002, F-005, F-007, F-008 (partial); engineering-frontend-developer on F-001, F-003, F-004 (done); left as is: F-002 (the `add_note` half) not fixed: `backend/app/ticket_services.py:366` is outside the writable list. The fix is `author_type="human" if ctx.user else "system"`. / F-008 (schema part) not done: `backend/app/schemas.py` is not writable. `TimesheetEntryOut` needs `entry_type`, and `TimesheetOut` needs `automation_minutes`. Until then `response_model` drops both new fields, so the user still cannot tell automation rows from labour rows in the API response. Row `entry_type` and `automation_minutes` are already in the `timesheet()` dict. / F-005 only documented. Returning null or adding an error boundary is a design choice. / F-007 not fixed. It needs a backfill migration in 0033 and a decision on cross-integration collisions, which is outside the writable files. / No new tests were added for F-001, F-002 or F-008 (automation entry on a project ticket, note with no user, automation row on a timesheet). / F-003 (partial): I kept the hard-coded Tailwind palette classes and did not move them to theme tokens. The repo has no violet token, so adding one is a design decision. The System badge and system note tone (`slate-*`) are unchanged, so they do not yet share the badge style. / F-004 (caveat): `role="status"` sits on an `li` that is only added when the list is empty. Some screen readers may not announce a live region that appears already filled. I did not add a persistent wrapper or filtered-count message, because that is a larger change.; checks 23/23 passed, 5 file(s) changed

## Coverage
No coverage data found (looked for coverage/coverage-summary.json, coverage-summary.json, coverage/lcov.info, lcov.info, coverage.xml, coverage/cobertura-coverage.xml, coverage/coverage.xml, coverage.txt, coverage/coverage.txt). Advisory only: run the test suite with coverage to check review.coverage_thresholds.
