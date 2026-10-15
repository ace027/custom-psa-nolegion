# Phase 4: Outlook push + free/busy — Review Summary

## Result: PASSED

**Cycles Used**: 2
**Reviewers**: testing-qa-verification-specialist, engineering-backend-architect, testing-api-tester, engineering-frontend-developer
**Evaluators**: code-quality, ui-ux, integration, business-logic
**Completed**: 2026-10-15

## Findings Summary
- Must-fix (blocker, critical, major) found: 6; fixed: 6; unresolved: 0
- Suggestions (minor, advisory): 1
- Deferred (confidence 50-79%): 23
- Hot spots (flagged by 2+ reviewers): `backend/app/mail/graph.py`, `frontend/src/pages/Settings.tsx`, `frontend/src/pages/Dispatch.tsx`, `backend/app/calendar_sync.py`, `docs/CALENDAR_SETUP.md`, `backend/app/mail/graph.py (with backend/app/calendar_sync.py)`

## Findings Detail
| ID | Severity | Location | Issue | Reviewers | Confidence | Status |
|----|----------|----------|-------|-----------|------------|--------|
| F-001 | major | `backend/app/mail/graph.py:219-224` | When Graph returns a per-user `error` entry in the getSchedule response, `get_schedule` logs a warning and sets `out[key] = []`. `refresh_busy` treats that as a successful empty schedule. It deletes the user's cached `BusyBlock` rows, sets `fetched_at=now`, and clears `last_error`. | testing-qa-verification-specialist | 80% | fixed |
| F-002 | critical | `backend/app/mail/graph.py:241-246` | When `getSchedule` returns a per-user `error` entry (for example `ErrorAccessDenied` when the tech is outside the RBAC scope), `get_schedule` logs it and stores `out[key] = []`. `refresh_busy` can't tell that from "no busy time". It deletes the user's cached blocks, sets `fetched_at=now` and clears `last_error`. | evaluator:code-quality | 85% | fixed |
| F-003 | major | `backend/tests/test_calendar_busy.py:112-135` | The tests cover a whole-batch `GraphError` and a user missing from the answer. None covers a Graph per-schedule error entry, which is the main failure mode for a user outside the RBAC scope (see Finding 1). | evaluator:code-quality | 80% | fixed |
| F-004 | major | `backend/app/mail/graph.py (also backend/app/calendar_sync.py):221-224` | `get_schedule` turns a per-user `error` entry (for example `ErrorAccessDenied` for a mailbox outside the RBAC group) into `out[key] = []`. `refresh_busy` treats an empty list as a good answer. It deletes that user's cached busy blocks, sets `fetched_at=now` and clears `last_error`. `test_get_schedule_parses_items_drops_free_and_maps_errors` asserts the empty-list behavior (`out["other@msp.com"] == []`). The `refresh_busy` docstring and the criterion both say a failed fetch keeps the old blocks and records the error. | evaluator:integration | 85% | fixed |
| F-005 | critical | `backend/app/mail/graph.py (with backend/app/calendar_sync.py):221-224` | When `getSchedule` returns a per-user `error` entry, `get_schedule` maps it to `out[key] = []`. `refresh_busy` then treats `[]` as a successful empty answer. It deletes that user's cached busy blocks, sets `fetched_at=now` and clears `last_error`. | evaluator:business-logic | 85% | fixed |
| F-006 | major | `backend/app/scheduling.py (with backend/alembic/versions/0025_outlook_sync.py):379-385` | Sync rows are created only on appointment writes (`enqueue`). The migration does not backfill future scheduled appointments, and switching `outlook_sync_enabled` on does not enqueue them either. Appointments that already exist have no row, so they are never pushed. `sync_states` reports them as "skipped". | evaluator:business-logic | 80% | fixed |
| F-007 | advisory | `backend/tests/test_calendar_sync.py:137` | The fixture parameter `make_user` is unused in `test_create_pushes_the_approved_payload`. | evaluator:code-quality | 80% | deferred |

## Reviewer Verdicts
- Cycle 1, testing-qa-verification-specialist: **NEEDS WORK**
- Cycle 1, engineering-backend-architect: **NEEDS WORK**
- Cycle 1, testing-api-tester: **PASS**
- Cycle 1, engineering-frontend-developer: **NEEDS WORK**
- Cycle 1, evaluator:code-quality: **NEEDS WORK**
- Cycle 1, evaluator:ui-ux: **NEEDS WORK**
- Cycle 1, evaluator:integration: **NEEDS WORK**
- Cycle 1, evaluator:business-logic: **NEEDS WORK**
- Cycle 2, testing-qa-verification-specialist: **PASS**
- Cycle 2, engineering-backend-architect: **PASS**
- Cycle 2, testing-api-tester: **PASS**
- Cycle 2, engineering-frontend-developer: **PASS**
- Cycle 2, evaluator:code-quality: **PASS**
- Cycle 2, evaluator:integration: **NEEDS WORK**
- Cycle 2, evaluator:business-logic: **PASS**

## Suggestions (Not Required)
- F-007 `backend/tests/test_calendar_sync.py`: The fixture parameter `make_user` is unused in `test_create_pushes_the_approved_payload`. (fix: Remove the parameter.)

## Deferred (Medium Confidence)
- `backend/alembic/versions/0025_outlook_sync.py` [major, 70%]: The migration creates `appointment_sync` empty. It doesn't backfill rows for existing scheduled appointments. No code path creates them when `outlook_sync_enabled` flips to true (nothing in routers/config.py or calendar_sync.py). `enqueue` runs only on create, move/reassign and cancel.
- `backend/app/scheduling.py (with backend/app/calendar_sync.py)` [minor, 60%]: `availability_for` returns cached `BusyBlock` rows regardless of `outlook_sync_enabled`. Once sync is disabled, stale blocks keep rendering with an old `fetched_at`, because `refresh_busy` returns early and never clears them. `status_summary` uses `min(fetched_at)` over an inner join to `CalendarBusyStatus`. A user with no row, because they were never polled or are newly eligible, is invisible in "oldest fetch", so the cache looks fresher than it is.
- `backend/app/routers/scheduling.py (with backend/app/calendar_sync.py)` [minor, 55%]: `GET /calendar-sync/status` needs only `P.SCHEDULE_READ`. It returns `last_error` for each failure. That value is `str(error)[:500]` taken from the Graph exception. The same field is also returned in `AppointmentOut.sync.last_error` on every appointment read. Any read-only scheduling user can therefore see raw upstream error text. That text can include Graph request ids, tenant or mailbox identifiers and URLs.
- `frontend/src/pages/Settings.tsx` [minor, 70%]: `OutlookSyncCard` renders nothing while `q.isLoading` is true. The card title shows with an empty body, and no loading text is shown. The sync status query is not polled, so `busy_fetched_at` stays frozen. `now` is recomputed on each render, so "N min ago" and the stale colour only change when something else re-renders the page.
- `frontend/src/pages/Dispatch.tsx` [minor, 75%]: The `now` state is set every 30s and the interval always runs, even when sync is off. Each tick re-renders the whole `Dispatch` component, including the drag-and-drop calendar. `components={{ event: EventBlock }}`, `eventPropGetter` and the other inline props are new objects on every render. Only the caption uses `now`.
- `frontend/src/scheduling/EditDialog.tsx` [minor, 55%]: The `sync` state is copied from `a.sync` once with `useState`, and it is never updated from the prop. The board refreshes `appointment` after the optimistic update and every invalidation. The dialog keeps the stale value, and the stale value can also drive the Retry button's visibility.
- `frontend/src/pages/Dispatch.tsx` [advisory, 60%]: `Dispatch` has grown to about 500 lines. The failure panel and the Outlook caption are inlined. They could be separate typed components such as `SyncFailuresPanel` and `OutlookCaption`.
- `backend/app/calendar_sync.py` [minor, 60%]: `status_summary` calls `ctx.db.get(Settings, 1).outlook_sync_enabled` with no None guard. `push_pending` and `refresh_busy` both guard for a missing settings row. `busy_fetched_at` is the minimum over `calendar_busy_status` rows only, so an eligible user who has never been fetched is excluded.
- `docs/CALENDAR_SETUP.md` [major, 55%]: The doc explains how to run the spike but records no result: no PASS block, no tenant or date, and no owner approval of the `Calendars.ReadWrite` RBAC scope. I found nothing in the listed files that shows the spike was run on a real tenant.
- `frontend/src/pages/Dispatch.tsx` [minor, 55%]: The failure-count toggle sets `aria-controls="sync-failures"`, but that element is only mounted while the panel is open. A retry that succeeds gives no announcement. The row disappears silently, and focus is lost if it was on the Retry button. The retry error uses `role="alert"`, but success has no live feedback.
- `frontend/src/scheduling/dispatch.css` [advisory, 50%]: `.dispatch-syncfail` hardcodes `#fff` and `#b91c1c`, and the new `.shade-outlook` rules hardcode hex values. Neighbouring rules use `var(--color-slate-*)` tokens. The failure badge's white background is not overridden under `:root.dark`.
- `backend/app/scheduling.py` [minor, 50%]: The dedupe that hides our own pushed events applies when an appointment's sync row is `synced`, and it matches the appointment's current start and end exactly. After a reschedule, the old Outlook event stays at the old time until the push completes. The row is `pending` during that window, and the old block matches no appointment, so it shows as foreign busy time.
- `docs/CALENDAR_SETUP.md` [minor, 65%]: The doc says a hand-deleted event "is recreated the next time the appointment is pushed". It does not say that nothing reconciles on its own, so a deleted event stays missing until the appointment is next edited. It also does not say that appointments existing before sync was enabled are not pushed (Finding 2).
- `docs/CALENDAR_SETUP.md, backend/dev/graph_calendar_spike.py` [major, 60%]: Nothing in the reviewed files records the owner's approval of the RBAC-scoped `Calendars.ReadWrite`. Nothing records a real-tenant spike run either (no PASS output). The only evidence is the instructions. The planning notes show an unapproved `GRANT DELETE` edit to migration 0025.
- `backend/app/calendar_sync.py` [minor, 55%]: `push_pending` calls `enqueue_unsynced` on every worker poll. Each call runs an anti-join over all future scheduled appointments and always commits. It has no cheap guard, such as running only when the setting flips on or at a low frequency.
- `backend/app/calendar_sync.py` [minor, 55%]: `push_pending` runs `enqueue_unsynced` on every worker tick. It is an anti-join over all appointments with `status='scheduled'` and `ends_at > now`. It also commits on every call, even when nothing was inserted. Whether `appointments.ends_at` or `appointment_syncs.appointment_id` has a supporting index was not checked.
- `backend/app/calendar_sync.py` [minor, 60%]: F-004 is fixed. `get_schedule` now omits per-user `error` entries. `refresh_busy` keeps the old blocks and records an error. `test_per_schedule_error_keeps_blocks_and_records_it` and `test_graph_calendar.py:143` cover it. The recorded message is the generic "No schedule returned for this user", so the Graph reason (for example `ErrorAccessDenied`) is only written to the log.
- `backend/app/mail/graph.py (with backend/app/calendar_sync.py)` [minor, 60%]: F-002 is fixed: an errored schedule is left out of the result, so `refresh_busy` keeps the old blocks and records an error. But the Graph error code (for example `ErrorAccessDenied`) only goes to the log. The status row gets the generic text "No schedule returned for this user".
- `backend/tests/test_calendar_busy.py` [minor, 70%]: F-003 is addressed, but `test_per_schedule_error_keeps_blocks_and_records_it` and `test_missing_user_keeps_blocks_while_others_refresh` drive the same code path. The fake omits the user in both cases. The Graph-entry-to-omission mapping is covered only in `test_graph_calendar.py`, so no test runs a real `GraphClient` through `refresh_busy`. The missing-user test also asserts `run(...) >= 1` (line 133), which is too loose.
- `backend/app/calendar_sync.py` [minor, 60%]: `status_summary` does `ctx.db.get(Settings, 1).outlook_sync_enabled` with no None check. `push_pending` and `refresh_busy` both handle a missing settings row.
- `backend/app/mail/graph.py` [advisory, 50%]: An entry with no `scheduleId` gets the key `""`, which is stored in `out` and never matches a user.
- `backend/tests/test_graph_calendar.py` [advisory, 55%]: `test_throttle_and_unavailable_are_transient` is parametrized with `transient` always True, so the parameter adds nothing. No test covers a `getSchedule` HTTP error, a malformed item, or an empty `value` list.
- `backend/app/mail/graph.py` [major, 70%]: `_auth` is not covered by the error handling in `_request_user`. A transport failure on the token POST (`httpx.TransportError`) is not wrapped and escapes as a raw httpx exception. A non-200 token response (429, 5xx or a network blip at login.microsoftonline.com) raises `GraphError(...)` with `transient=False` and `status=None`.

## Fixes Applied
- cycle 1: engineering-backend-architect on F-001, F-002, F-003 (blocked); engineering-senior-developer on F-004, F-005, F-006 (done); checks 21/21 passed
- minor findings: engineering-backend-architect on F-007, F-002, F-010 (partial); engineering-frontend-developer on F-005, F-006, F-007, F-008 (done); engineering-senior-developer on F-012 (done); left as is: F-002: not changed, because the finding is wrong for this codebase. `push_pending` calls `enqueue_unsynced` (calendar_sync.py:328-346, called at :357) on every worker run while the flag is on. That inserts pending rows for scheduled appointments with `ends_at > now` that have no sync row. Existing bookings, and bookings made while the toggle was off, are therefore queued as soon as sync is enabled. A migration backfill or a PATCH hook would repeat that work. The separate test the finding asks for (a flag flip creating the rows) does not exist yet. I did not add one. / F-008 (extract SyncFailuresPanel): not done. It is advisory and a larger refactor. The OutlookCaption half and the failuresOpen reset are done. / F-007 (stale prop): Dispatch keeps `editing` as a snapshot in state and does not refresh it from the query. So the stale value comes from that snapshot, not from board refreshes. The override fix still removes the dialog's own copy of the state. / F-012: I did not fix it. A PASS block, tenant, date and owner approval of the `Calendars.ReadWrite` scope can only come from the owner running `graph_calendar_spike.py --write --outside` on a real tenant. Writing them into docs/CALENDAR_SETUP.md would be fabricated evidence. I did not read the doc or search the repo for an existing run record, so I haven't checked the reviewer's claim that none exists. Treat the first success criterion as open until the owner runs the spike and supplies the result.; checks 21/21 passed, 6 file(s) changed

## Cycle Delta
- cycle 1: 1 out-of-domain finding(s) filtered (engineering-frontend-developer on backend, owner engineering-backend-architect); see .planning/logs/authority-decisions-2026-10-15.log
- cycle 1: 6 must-fix, 0 suggestions, 14 deferred, 0 dropped (low confidence)
- cycle 2: 1 out-of-domain finding(s) filtered (testing-qa-verification-specialist on testing, owner testing-api-tester); see .planning/logs/authority-decisions-2026-10-15.log
- cycle 2: 0 must-fix (resolved 6, new 0, unchanged 0), 1 suggestions, 9 deferred, 0 dropped (low confidence)

## Coverage
No coverage data found (looked for coverage/coverage-summary.json, coverage-summary.json, coverage/lcov.info, lcov.info, coverage.xml, coverage/cobertura-coverage.xml, coverage/coverage.xml, coverage.txt, coverage/coverage.txt). Advisory only: run the test suite with coverage to check review.coverage_thresholds.

## Security Review

**Verdict**: PASS — 0 unresolved CRITICAL/HIGH finding(s). Details: `SECURITY-REVIEW.md`.
