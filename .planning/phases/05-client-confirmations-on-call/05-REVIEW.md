# Phase 5: Client confirmations + on-call — Review Summary

## Result: PASSED

**Cycles Used**: 1
**Reviewers**: testing-qa-verification-specialist, engineering-senior-developer, design-ux-researcher, design-ui-designer
**Evaluators**: code-quality, ui-ux, integration, business-logic
**Completed**: 2026-10-15

## Findings Summary
- Must-fix (blocker, critical, major) found: 0; fixed: 0; unresolved: 0
- Suggestions (minor, advisory): 1
- Deferred (confidence 50-79%): 27
- Hot spots (flagged by 2+ reviewers): `backend/app/scheduling.py`, `backend/app/portal.py`, `backend/app/client_notices.py`, `frontend/src/pages/OnCall.tsx`, `frontend/src/portal/AppointmentsPage.tsx`, `frontend/src/scheduling/BookingDialog.tsx`, `frontend/src/OnCallWidget.tsx`, `frontend/src/portal/PortalApp.tsx`

## Findings Detail
| ID | Severity | Location | Issue | Reviewers | Confidence | Status |
|----|----------|----------|-------|-----------|------------|--------|
| F-001 | advisory | `backend/app/client_notices.py:123` | Three small leftovers. The `label` dict in `_render` maps each key to itself, so it adds nothing. `_decide` takes the parameter `n`, which it never uses. `settings_url()` has a misleading name (it returns the public URL, not a settings page) and imports `get_settings` inside the function. | evaluator:code-quality | 85% | deferred |

## Reviewer Verdicts
- Cycle 1, testing-qa-verification-specialist: **NEEDS WORK**
- Cycle 1, engineering-senior-developer: **PASS**
- Cycle 1, design-ux-researcher: **NEEDS WORK**
- Cycle 1, design-ui-designer: **NEEDS WORK**
- Cycle 1, evaluator:code-quality: **PASS**
- Cycle 1, evaluator:ui-ux: **NEEDS WORK**
- Cycle 1, evaluator:integration: **PASS**
- Cycle 1, evaluator:business-logic: **NEEDS WORK**

## Suggestions (Not Required)
- F-001 `backend/app/client_notices.py`: Three small leftovers. The `label` dict in `_render` maps each key to itself, so it adds nothing. `_decide` takes the parameter `n`, which it never uses. `settings_url()` has a misleading name (it returns the public URL, not a settings page) and imports `get_settings` inside the function. (fix: Use `kind` directly in the subject. Remove the `n` parameter from `_decide`. Rename `settings_url` to `_public_url` and import `get_settings` at module level unless that causes an import cycle.)

## Deferred (Medium Confidence)
- `backend/app/scheduling.py` [major, 65%]: `update_appointment` only queues a notice when the time changes or when the appointment becomes notifiable. If an appointment that was already emailed gets `client_visible=False` or `notify_client=False`, no notice is queued. `client_notices.queue` also returns early for a non-notifiable appointment, so a cancellation email can never be produced. The portal list filters on `client_visible`, so the visit just vanishes from the portal.
- `backend/app/portal.py` [minor, 60%]: The query orders by `starts_at` ascending and applies `.limit(200)`. The window starts 30 days in the past and has no upper bound, so with more than 200 rows the oldest ones fill the limit and the upcoming appointments are cut off.
- `backend/app/client_notices.py` [minor, 55%]: `send_due` handles up to 50 due notices in one transaction with a single `db.commit()` at the end, and `worker.client_notice_jobs` catches any exception and does nothing else. If one row raises (a DB constraint error, or a bad `tech_id` or `contact` row), the whole batch rolls back. The same ordered batch (`send_after`, `id`) is picked up on the next cycle and fails the same way.
- `backend/app/scheduling.py` [minor, 60%]: `appointment_view` looks up the client notice only inside `if sync is None:`. A caller that passes `sync` but leaves `notice` unset gets `notice=None`, with no error. When `sync` is missing, the function falls back to per-appointment queries (`sync_states`, `latest_for`, then `db.get` for the org, ticket and tech), which is an N+1 pattern if used in a loop.
- `frontend/src/portal/appointments.ts` [advisory, 50%]: `dateLabel` and `timeRange` format with the browser's locale and timezone, not the org timezone. The scheduling code uses `getOrgTimezone` for the same purpose, and the portal helpers do not reuse any shared formatter.
- `frontend/src/pages/OnCall.tsx` [major, 70%]: The override Delete button removes the override immediately. There is no confirmation and no undo. The button's disabled state is shared across the whole list (`del.isPending`), and no success message appears.
- `frontend/src/pages/OnCall.tsx` [minor, 55%]: The page does not show "who is on call now". Only the sidebar widget does, and the page has no current-holder banner. The override form also appears fully expanded on every rotation card. With several rotations the page repeats the same four-field form and the Overrides list on each card.
- `frontend/src/portal/AppointmentsPage.tsx` [minor, 60%]: The page has no `<h1>` or page heading. The empty state reads "No appointments scheduled" and does not mention the 30-day past window. The loading state is a bare "Loading…" with no `role="status"`. Each row's link text combines the ticket number and subject, with no context such as "View ticket".
- `frontend/src/scheduling/BookingDialog.tsx` [minor, 60%]: The "Don't email client" checkbox is a negative toggle, and the dialog never says which contact will receive the email. The brief requires the email to go to "the chosen contact". The booking UI shows no recipient.
- `frontend/src/OnCallWidget.tsx` [minor, 55%]: The widget swallows query errors with `retry: false` and returns null on error. The user cannot tell "no rotations" apart from "failed to load". The "until" line also disappears silently if the timezone query is slow or fails.
- `frontend/src/pages/OnCall.tsx` [minor, 75%]: The member order is rendered as a single text line joined with double spaces (`1. A  2. B`). HTML collapses the double spaces, so the names run together as "1. Ann 2. Bob" with no separators.
- `frontend/src/pages/OnCall.tsx` [minor, 70%]: The shift table has no `<caption>` or `aria-label`, and its `<th>` elements have no `scope="col"`. It also has no cell padding (`px-2 py-1`), so columns sit flush against each other. Override rows are not visually distinguished from rotation rows beyond the text in the last column.
- `frontend/src/pages/OnCall.tsx` [major, 65%]: "Delete" removes an override immediately, with no confirmation and no undo. `del.isPending` disables every Delete button in the card, and the buttons keep the same label while deleting.
- `frontend/src/pages/OnCall.tsx` [minor, 60%]: If the anchor date does not match the handoff weekday, the submit button is disabled and an error shows below the grid. The error is not tied to the anchor input with `aria-describedby` or `aria-invalid`. Changing the weekday silently rewrites the anchor date.
- `frontend/src/pages/OnCall.tsx` [advisory, 50%]: The Up, Down and Remove buttons use the same secondary style and sit next to each other. The destructive Remove has no visual distinction. After a move, focus follows neither the item nor the button, because the list is re-keyed by user id and the focused button may become disabled.
- `frontend/src/portal/PortalApp.tsx` [minor, 55%]: The tab `<nav>` has no `aria-label`, and the row `flex gap-1` does not wrap. Adding a fourth tab, Appointments, makes the row wider and it can overflow on 320px screens.
- `backend/app/worker.py` [advisory, 50%]: `client_notice_jobs()` runs only in the mail-configured loop. In the "mail not configured" idle loop it never runs, although `billing_jobs`, `notify_jobs` and `integration_jobs` do.
- `frontend/src/pages/OnCall.tsx` [major, 60%]: The override form does not check that the end is after the start, and it does not check that the pair parses. `new Date(v)` on an empty or odd string yields an Invalid Date. The form has no inline validation, no `role="alert"` message and no `min` attribute on the end field.
- `frontend/src/portal/AppointmentsPage.tsx` [minor, 55%]: Each row shows a date, a time range and a link, but gives no status or cancelled indication. The time range is shown with no timezone. The portal does not say which zone the times are in, so a client in another zone is misled.
- `frontend/src/scheduling/BookingDialog.tsx` [minor, 60%]: `SlotInputs` uses `grid-cols-3` at every width, inside a `max-w-lg` modal. On a 320px viewport the three inputs (a date and two times) are about 90px wide each. The "Ends the next day." note (line 93) is a plain `<p>` and is not announced when it appears.
- `frontend/src/scheduling/BookingDialog.tsx` [minor, 55%]: The "Don't email client" checkbox is a negative-phrased option that appears only when "Visible to client" is on. Unchecking "Visible" silently drops the email choice. The dialog does not say that a client will be emailed by default.
- `frontend/src/scheduling/EditDialog.tsx` [minor, 50%]: The sync status line distinguishes the failed state with a "✖" prefix, which is marked `aria-hidden`. The text "Outlook sync failed" carries the meaning, so that is fine. The reschedule-email choice is different. `a.client_visible && noEmail !== …` is checked, but when the time changes and "Don't email client" is checked, nothing tells the user that the client will not be told about the move. The notice line (`noticeLine`) is shown only after saving, not before.
- `frontend/src/scheduling/EditDialog.tsx` [minor, 70%]: The cancel-confirm panel opens inline at the bottom. Focus stays on the "Cancel appointment" button, which unmounts when `confirming` becomes true. Focus is lost to the body, and the Modal's focus trap then has no active element.
- `frontend/src/scheduling/BookingDialog.tsx` [minor, 50%]: The ticket search results are a list of buttons. When the search field has text, search results load with no live announcement, and the result list has no `aria-live`. Result buttons have `hover:bg-slate-100` but no focus style.
- `backend/app/oncall_service.py` [major, 60%]: `_check_users` verifies that users are active only when members or overrides are written. `now()`, `schedule()` and `oncall.who_is_on` never re-check it. A member deactivated after being added stays in the rotation, and an override for a deactivated user stays valid. The who's-on-call display and shift list then name someone who has left. The tests cover inactive users only at creation time (`test_unknown_or_inactive_members_are_422`).
- `backend/app/oncall_service.py` [minor, 55%]: `update_rotation` applies a change to `anchor_date`, `handoff_weekday`, `handoff_time` or `member_ids` immediately and to the whole timeline. The week index is `(at - anchor) // 7 days` and the person is `members[k % n]`. Reordering, adding or removing a member, or moving the anchor, therefore silently changes who is on call right now and who was on call in past weeks. Nothing keeps the current assignee stable or warns the caller, and there is no effective-from date.
- `backend/app/client_notices.py, /home/user/custom-psa-nolegion/backend/app/worker.py` [minor, 55%]: `_decide` never checks whether the appointment has already ended. `client_notice_jobs` also runs only in the mail-configured loop, so notices stay pending while mail is unconfigured. When mail is later configured, every stale pending notice becomes an outbound "booked" or "moved" email, including ones for visits that are already over.

## Fixes Applied
- minor findings: engineering-backend-architect on F-001, F-001, F-002, F-003, F-004, F-005 (partial); engineering-frontend-developer on F-006, F-007 (done); left as is: scheduling.py F-001 (major): not fixed. Sending or suppressing a cancellation email when an appointment is hidden or muted is a product decision. The alternative is to document the current behavior and pin it in a test. / portal appointments.ts F-005: not fixed. It needs a portal API change to return the org timezone, plus a shared formatter, which is a cross-module design change. / I did not add tests for the new per-row error handling or the portal limit split. / F-006 (not fixed): the "disabled state shared across the whole list (del.isPending)" point is still there. It is only disabled for the duration of one request, so I left it. / F-006 (not fixed): no success message after delete. The row disappears when the list refreshes, and a message would be a design decision.; checks 16/16 passed, 5 file(s) changed

## Coverage
No coverage data found (looked for coverage/coverage-summary.json, coverage-summary.json, coverage/lcov.info, lcov.info, coverage.xml, coverage/cobertura-coverage.xml, coverage/coverage.xml, coverage.txt, coverage/coverage.txt). Advisory only: run the test suite with coverage to check review.coverage_thresholds.

## Security Review

**Verdict**: PASS — 0 unresolved CRITICAL/HIGH finding(s). Details: `SECURITY-REVIEW.md`.
