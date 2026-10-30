# Phase 11: Reporting & dashboards — Review Summary

## Result: PASSED

**Cycles Used**: 2
**Reviewers**: testing-qa-verification-specialist, engineering-frontend-developer, design-ux-architect, engineering-senior-developer
**Evaluators**: code-quality, ui-ux, integration, business-logic
**Completed**: 2026-10-30

## Findings Summary
- Must-fix (blocker, critical, major) found: 2; fixed: 2; unresolved: 0
- Suggestions (minor, advisory): 3
- Deferred (confidence 50-79%): 31
- Hot spots (flagged by 2+ reviewers): `backend/app/report_schedules.py`, `frontend/src/pages/reports/SlaReport.tsx`, `frontend/src/pages/reports/ReportSchedules.tsx`, `frontend/src/pages/Dashboard.tsx`, `backend/app/dashboards.py`, `frontend/src/Dashboards.test.tsx`, `frontend/src/pages/Users.tsx`

## Findings Detail
| ID | Severity | Location | Issue | Reviewers | Confidence | Status |
|----|----------|----------|-------|-----------|------------|--------|
| F-001 | minor | `frontend/src/pages/reports/ReportSchedules.tsx:108-115` | The schedule runs table has no `<caption>` or accessible name. Its header cells (`<th>`) have no `scope="col"`. The report tables built with `ReportTable` in `SlaReport.tsx` have both. | engineering-frontend-developer, design-ux-architect | 85% | deferred |
| F-002 | major | `frontend/src/pages/reports/SlaReport.tsx:461-469` | `ReportTable` wraps wide tables (up to 70rem) in an `overflow-x-auto` div. The div has no `tabIndex`, `role="region"` or `aria-label`. | evaluator:ui-ux | 85% | fixed |
| F-003 | major | `frontend/src/pages/Users.tsx:46` | The per-row role `<select>` has no accessible name, because the table cell is its only context. The Deactivate/Activate buttons lack the user's name, while the Edit button has an `aria-label`. The Edit button actually opens the cost-rate form, and its visible label doesn't say that. | evaluator:ui-ux | 85% | fixed |
| F-004 | minor | `frontend/src/pages/Users.tsx:35-38` | The users table has no `<caption>` and no `scope="col"` on its headers. The trailing `<th />` is an empty header cell for the actions column. | design-ux-architect, evaluator:ui-ux | 85% | deferred |
| F-005 | minor | `frontend/src/pages/Users.tsx:60-62` | The button's visible text is "Close" while it is open, but its `aria-label` is always "Cost rate for {name}". The accessible name does not contain the visible label, which fails WCAG 2.5.3 Label in Name. The earlier fix of F-003 is otherwise in place: the role select, the Deactivate/Activate button and the cost-rate button all have names that include the user. | evaluator:ui-ux | 80% | deferred |

## Reviewer Verdicts
- Cycle 1, testing-qa-verification-specialist: **NEEDS WORK**
- Cycle 1, engineering-frontend-developer: **NEEDS WORK**
- Cycle 1, design-ux-architect: **NEEDS WORK**
- Cycle 1, engineering-senior-developer: **NEEDS WORK**
- Cycle 1, evaluator:code-quality: **NEEDS WORK**
- Cycle 1, evaluator:ui-ux: **NEEDS WORK**
- Cycle 1, evaluator:integration: **NEEDS WORK**
- Cycle 1, evaluator:business-logic: **NEEDS WORK**
- Cycle 2, testing-qa-verification-specialist: **PASS**
- Cycle 2, engineering-frontend-developer: **PASS**
- Cycle 2, design-ux-architect: **PASS**
- Cycle 2, engineering-senior-developer: **PASS**
- Cycle 2, evaluator:ui-ux: **NEEDS WORK**

## Suggestions (Not Required)
- F-001 `frontend/src/pages/reports/ReportSchedules.tsx`: The schedule runs table has no `<caption>` or accessible name. Its header cells (`<th>`) have no `scope="col"`. The report tables built with `ReportTable` in `SlaReport.tsx` have both. (fix: Add `<caption className="sr-only">Runs for {schedule name}</caption>` and `scope="col"` on each `<th>`. Alternatively, reuse `ReportTable`.)
- F-004 `frontend/src/pages/Users.tsx`: The users table has no `<caption>` and no `scope="col"` on its headers. The trailing `<th />` is an empty header cell for the actions column. (fix: Add `<caption className="sr-only">Users</caption>`. Add `scope="col"` to each `<th>`. Replace the empty `<th />` with `<th scope="col"><span className="sr-only">Actions</span></th>`.)
- F-005 `frontend/src/pages/Users.tsx`: The button's visible text is "Close" while it is open, but its `aria-label` is always "Cost rate for {name}". The accessible name does not contain the visible label, which fails WCAG 2.5.3 Label in Name. The earlier fix of F-003 is otherwise in place: the role select, the Deactivate/Activate button and the cost-rate button all have names that include the user. (fix: Make the label follow the visible text: `aria-label={rateFor === u.id ? `Close cost rate for ${u.display_name}` : `Cost rate for ${u.display_name}`}`. Alternatively, keep the visible text and add the name in an `sr-only` span.)

## Deferred (Medium Confidence)
- `backend/app/report_schedules.py` [major, 75%]: A "failed" run row is written with the same (schedule_id, period_start) key as a successful one. The "already done" check on lines 221-228 treats any run row as done. One transient failure, such as a DB hiccup or a report query error, is therefore never retried for that period.
- `backend/app/report_schedules.py` [minor, 50%]: `due_period` only ever returns the most recent period. If the worker is down across a whole period boundary (a weekly schedule for more than a week, a monthly one for more than a month), the missed period is skipped with no run row and no notice. Re-enabling a schedule with `active=false` and then `true` also silently skips the intervening periods.
- `frontend/src/pages/reports/SlaReport.tsx` [minor, 60%]: `useRange` passes the raw date input values straight into the query key, the query function and the CSV href. Clearing a date input yields `""`, and `from` can be set later than `to`. The report then fetches with an empty or inverted range and the Download CSV link points at the same bad URL. The SLA, utilisation and profitability pages all share this hook.
- `frontend/src/pages/Dashboard.tsx` [minor, 65%]: The main dashboard query has no loading state. `ErrorMsg` is shown with no Retry button, unlike `MyWeek` and `Business`, which use `QueryStatus`. While `/dashboard` loads, the three sections above it already render and the rest of the page is blank. If the query fails, the user gets no retry.
- `frontend/src/pages/reports/SlaReport.tsx` [advisory, 55%]: The `Download CSV` link is a small `text-sm` inline anchor with no padding. The same pattern appears in the other three reports.
- `frontend/src/pages/reports/ReportSchedules.tsx` [minor, 60%]: Activate/Deactivate and save/cancel outcomes are not announced. The button label and the "active/inactive" text change silently. Focus is not managed after the toggle, and there is no live region.
- `frontend/src/pages/reports/ReportSchedules.tsx` [minor, 60%]: The `<form>` has no accessible name. It sits inline, and the Edit/New form is not marked as a region. The hint "Select at least one recipient" explains why Submit is disabled, but it is not linked to the button through `aria-describedby` and is not announced.
- `frontend/src/pages/reports/SlaReport.tsx` [minor, 55%]: The "Loading..." `role="status"` paragraph is mounted together with its text. Live regions injected with content already in them are often not announced. The same applies to `ErrorMsg` if it lacks `role="alert"`; I could not see its implementation. Errors also render as a plain sibling of the Retry button, with no association.
- `frontend/src/pages/reports/SlaReport.tsx` [advisory, 50%]: The two-row header uses `rowSpan`, `colSpan` and `scope="colgroup"`. The sub-headers under each group ("Breached", "Pending", "p50"...) rely on sr-only prefixes to carry their group. The bar column's header exists only as sr-only text.
- `frontend/src/pages/Dashboard.tsx` [minor, 65%]: Link tiles define only `hover:border-blue-400` and no explicit `focus-visible` style. Warning state (amber) is shown only by colour (border and background), with no text or icon.
- `backend/app/report_metrics.py, backend/app/report_schemas.py` [minor, 75%]: `REPORTS = ("sla", "utilisation", "aging", "profitability")` is never used anywhere in `app`. `report_schemas.ReportName` repeats the same four names as a separate `Literal`. `csv_for` also hard-codes them in its `if/elif` chain. The migration CHECK and the frontend `REPORT_NAMES` hold two more copies.
- `backend/app/routers/reports.py` [minor, 70%]: `_metric_csv` gets the CSV text back from `metrics.csv_for`, then re-parses it with `csv.reader` just to count rows for the export audit. The caller already built those rows. The `params` it records (`from`/`to` as passed in) can also differ from the effective range, because `csv_for` applies the default range internally.
- `backend/app/dashboards.py` [minor, 70%]: `me()` calls `metrics.utilisation` for every staff user, with its holiday, time-off, work-hours and `free_windows` computation per user. It then keeps only the calling user's row.
- `backend/app/routers/reports.py, backend/app/routers/dashboards.py` [advisory, 55%]: The role dashboards are split across two routers. `/dashboard/me` is in `routers/dashboards.py`, but the manager dashboard is `/reports/dashboard` in `routers/reports.py`. The scheduled-email endpoints are in `reports.py` as well, which also holds the older billing reports.
- `backend/app/report_schedules.py` [advisory, 60%]: `_validate_recipients` has its own copy of the "active and holds `REPORT_READ`" check, separate from `_eligible`. The loop in `_send_one` rebuilds `{e.lower() for e in emails}` on every iteration.
- `frontend/src/pages/reports/ReportSchedules.tsx` [minor, 60%]: `holdsReportRead` hardcodes the roles `admin` and `billing`. The backend decides this through `P.has_permission(role, REPORT_READ)`.
- `backend/tests/test_seed_and_migrations.py` [minor, 70%]: The test asserts that `alembic_version` equals `"0032"` exactly.
- `frontend/src/Dashboards.test.tsx` [minor, 60%]: The only report page tests are for the SLA report and the schedules page. `AgingReport.tsx`, `UtilisationReport.tsx` and `ProfitabilityReport.tsx` have no render, CSV-link, empty-state or error-state tests.
- `frontend/src/App.tsx` [minor, 65%]: The "Reports" nav group label uses `text-slate-400` at `text-xs`. On a light sidebar, slate-400 is about 2.6:1 contrast.
- `frontend/src/pages/Users.tsx` [minor, 70%]: The `<th>` header cells have no `scope="col"`, the table has no caption, and it is not in an overflow wrapper. The report tables use all three.
- `frontend/src/pages/Users.tsx` [minor, 60%]: The cost-rate validation message (`role="alert"`) is not tied to the input with `aria-describedby`. Focus is not moved to the form when it opens.
- `frontend/src/pages/reports/ReportSchedules.tsx` [minor, 60%]: While a form is open, the "New schedule" and "Edit" buttons are set to `disabled`. The explanation is in a `title`, which is unavailable to keyboard and touch users. Disabled buttons also drop out of the tab order.
- `frontend/src/pages/reports/ReportSchedules.tsx` [minor, 65%]: The Runs table is not in an overflow container. Its headers have no `scope`, and it has no caption. The status is shown as raw text with no visual distinction between success and failure. The Runs button sets `aria-controls` to `runs-${id}`, an element that doesn't exist while collapsed.
- `frontend/src/pages/reports/ReportSchedules.tsx` [advisory, 55%]: The UI copy shows the raw permission string "report:read" to managers.
- `frontend/src/pages/Dashboard.tsx` [minor, 65%]: Warning tiles differ only by amber colour and border. The same tile pattern exists twice, as `Stat` (text-2xl) and `Tile` (text-xl). Every 60-second poll dims the content to `opacity-60`, which drops text contrast below 4.5:1. The dimming also flickers on the whole dashboard.
- `frontend/src/pages/reports/SlaReport.tsx` [minor, 60%]: `useRange` does not validate the date range. A blank date, or From later than To, still fires the query and shows an API error or an empty-range message. All range reports share it.
- `backend/app/report_metrics.py` [major, 60%]: `_Clock.add` counts any unfinished ticket with `now > due` as breached. It ignores that the ticket may be in a clock-stopped status (for example waiting on the customer). `ticket_services` moves `sla_first_response_due` and `sla_resolution_due` only on resume (`recompute_sla`), so while a ticket is paused the stored due date is stale. The ticket dashboard's `sla_state` returns `paused` for these tickets, not `breached`.
- `backend/app/worker.py` [minor, 50%]: When mail is not configured, the idle loop still runs `report_jobs()`, which records scheduled reports as `sent`. Nothing ever calls `send_pending` in that branch, so the queued emails stay `pending` indefinitely.
- `frontend/src/Dashboards.test.tsx` [minor, 75%]: Nothing tests the F-002 and F-003 fixes: the named scroll region on the SLA table, the "Role for Tom" select name, or the "Deactivate Tom" button name. The SLA tests never change Group by, so the CSV href is only checked for `group=priority`. They also cover no error and Retry branch and no empty-rows branch. Dashboards are covered only for tech and billing roles, not for the admin or manager variants.
- `frontend/src/pages/reports/SlaReport.tsx` [minor, 65%]: The From and To dates are not validated. If From is later than To, the query fires anyway and the UI shows the "No tickets were created in this range." message. The CSV link is built from the same range.
- `frontend/src/pages/reports/SlaReport.tsx` [advisory, 55%]: Null values are rendered as a bare "-". Screen readers announce this as "dash" or nothing. `PctBar` accepts a `label` prop and never uses it.

## Fixes Applied
- cycle 1: engineering-frontend-developer on F-002, F-003 (done); checks 16/16 passed
- minor findings: engineering-frontend-developer on F-001, F-004, F-005, F-003, F-005, F-006 (partial); engineering-backend-architect on F-001, F-002 (partial); left as is: F-003 (UtilisationReport.tsx, ProfitabilityReport.tsx): not fixed. Both pages need `enabled: valid` and the CSV gating, but I may not write those files. Once `valid` is added to their `useRange()` destructuring, each is a small edit. / F-006 (billing/Reports.tsx): not fixed. It defines its own local `dl` constant and is outside my writable files. The shared `dl` change covers the four reports that import it. / F-002 (docs and test not done): `due_period` returns only the latest period, and I wrote no "missed" run row or test. A marker would need a design decision about backfill and how it would show in run history. The behaviour is documented only in the `due_period` docstring, and docs/REPORTS.md would need updating separately. / F-001 (design choice): I stored the attempt count in `detail` because adding an attempts column needs a migration, which is outside the files I may write. The runtime role also has no DELETE grant on report_schedule_runs, so I update the failed row in place instead of deleting and re-inserting it.; checks failed (2/16), changes undone

## Cycle Delta
- cycle 1: 1 out-of-domain finding(s) filtered (design-ux-architect on frontend, owner engineering-frontend-developer); see .planning/logs/authority-decisions-2026-10-30.log
- cycle 1: 2 must-fix, 1 suggestions, 28 deferred, 0 dropped (low confidence)
- cycle 2: 1 out-of-domain finding(s) filtered (engineering-senior-developer on accessibility, owner design-ux-architect); see .planning/logs/authority-decisions-2026-10-30.log
- cycle 2: 0 must-fix (resolved 2, new 0, unchanged 0), 2 suggestions, 3 deferred, 0 dropped (low confidence)

## Coverage
No coverage data found (looked for coverage/coverage-summary.json, coverage-summary.json, coverage/lcov.info, lcov.info, coverage.xml, coverage/cobertura-coverage.xml, coverage/coverage.xml, coverage.txt, coverage/coverage.txt). Advisory only: run the test suite with coverage to check review.coverage_thresholds.
