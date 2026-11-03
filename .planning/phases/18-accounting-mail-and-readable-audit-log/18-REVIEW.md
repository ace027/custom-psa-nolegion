# Phase 18: Accounting mail and readable audit log — Review Summary

## Result: PASSED

**Cycles Used**: 2
**Reviewers**: testing-qa-verification-specialist, design-ui-designer, design-ux-researcher, engineering-frontend-developer
**Evaluators**: code-quality, ui-ux, integration, business-logic
**Completed**: 2026-11-03

## Findings Summary
- Must-fix (blocker, critical, major) found: 2; fixed: 2; unresolved: 0
- Suggestions (minor, advisory): 0
- Deferred (confidence 50-79%): 12
- Hot spots (flagged by 2+ reviewers): `frontend/src/pages/Audit.tsx`, `frontend/src/pages/admin/settings/MailCalendarSettings.tsx`, `frontend/src/pages/Audit.test.tsx`

## Findings Detail
| ID | Severity | Location | Issue | Reviewers | Confidence | Status |
|----|----------|----------|-------|-----------|------------|--------|
| F-001 | blocker | `frontend/src/pages/Audit.tsx:34` | The page types `/audit/entity-types` as `string[]`. The backend (`backend/app/routers/users.py` lines 142-152) returns `[{"value": ..., "label": ...}]`. The page does `types.data?.map((t) => <option key={t} value={t}>{t}</option>)`, so `t` is an object. React throws "Objects are not valid as a React child" as soon as the query succeeds with any audit data. Every `key` would also be `[object Object]`. The test mock in `Audit.test.tsx` line 20 returns `["contact"]`, which hides the mismatch, so the tests pass against a contract the server does not honour. [OVERRIDE] Out-of-domain blocker kept per severity rule (domain owner: design-ux-researcher) | testing-qa-verification-specialist, design-ux-researcher, engineering-frontend-developer, evaluator:code-quality, evaluator:business-logic | 95% | fixed |
| F-002 | major | `frontend/src/pages/Audit.test.tsx:17-20` | The mock for `/audit/entity-types` does not match the API contract (strings instead of `{value, label}`). No test checks the frontend against the real response shape. | evaluator:code-quality, evaluator:business-logic | 90% | fixed |

## Reviewer Verdicts
- Cycle 1, testing-qa-verification-specialist: **NEEDS WORK**
- Cycle 1, design-ui-designer: **NEEDS WORK**
- Cycle 1, design-ux-researcher: **PASS**
- Cycle 1, engineering-frontend-developer: **NEEDS WORK**
- Cycle 1, evaluator:code-quality: **NEEDS WORK**
- Cycle 1, evaluator:ui-ux: **NEEDS WORK**
- Cycle 1, evaluator:integration: **PASS**
- Cycle 1, evaluator:business-logic: **NEEDS WORK**
- Cycle 2, testing-qa-verification-specialist: **PASS**
- Cycle 2, design-ui-designer: **PASS**
- Cycle 2, design-ux-researcher: **PASS**
- Cycle 2, engineering-frontend-developer: **PASS**
- Cycle 2, evaluator:code-quality: **PASS**

## Suggestions (Not Required)
(none)

## Deferred (Medium Confidence)
- `backend/app/mail/ingest.py (with backend/app/mail/graph.py line 222)` [minor, 55%]: `access_denied` is true for every HTTP 403, not only the permission codes. In `send_pending`, one such 403 marks the notice `failed` on its first attempt, with a "not allowed to send as … add to mailbox scope" message. A 403 from throttling-style tenant policy or a transient Exchange condition is therefore reported as a scope problem and never retried. A fixed mailbox scope does not requeue the already-failed statements.
- `frontend/src/pages/admin/settings/MailCalendarSettings.tsx` [minor, 60%]: The accounting address is saved by a plain `Button` that is not inside a `<form>`. Pressing Enter in the field does nothing, and the browser's `type="email"` check never runs. For example, an admin types "accounting" and presses Enter, and nothing happens. After clicking Save, the Save button disappears (`value` resets to null) with no confirmation message, so the admin cannot tell it worked.
- `frontend/src/pages/Audit.tsx` [minor, 70%]: While `/audit` is loading, `q.data` is undefined. The panel then renders an empty bordered box with no loading text. The same happens after any filter change, because the query key changes and there is no `placeholderData`. The user sees the list vanish and an empty box until the response arrives.
- `frontend/src/pages/Audit.tsx` [minor, 70%]: Every entry's toggle button says "Show raw" and does not change to "Hide raw" once expanded. The button has no entry-specific accessible name, so a screen reader hears 50 identical buttons. The class string has no focus style, and the touch target is tiny (text-xs).
- `backend/app/routers/users.py` [minor, 60%]: The router imports the private helpers `_bounds` and `_zone` from `app.report_metrics`.
- `backend/app/models.py` [advisory, 55%]: The `@validates` method sits between column definitions, in the middle of the `Settings` class (before `escalation_bump_priority`).
- `frontend/src/pages/Audit.tsx` [minor, 55%]: A date range where From is later than To is not checked. There is no "Clear filters" control. "Record type" options show raw entity type identifiers such as `ticket_note`. The "Action starts with" field is a raw-text filter that exposes the internal action code.
- `frontend/src/pages/Audit.tsx` [minor, 60%]: The paging buttons are unstyled apart from the disabled style. They have no focus or hover style and no minimum touch-target size. Other pages use the shared `Button`. The raw `←`/`→` characters are included in the accessible names.
- `frontend/src/pages/admin/settings/MailCalendarSettings.tsx` [advisory, 50%]: The mailbox status uses colour-only text (green, red, amber) for state, though the text also carries the status word. Grid placement of the new `dt`/`dd` pair puts "Billing mail is sent from" in a 4-column layout where the long label can wrap awkwardly on narrow screens.
- `backend/app/notices.py` [minor, 55%]: `send_notice` sets `from_email` to the accounting mailbox for every notice kind, including `kind == "invoice"`. docs/MAIL_SETUP.md:62 also says invoice emails come from the accounting mailbox. The criterion says only statements and reminders come from accounting, and everything else comes from the support mailbox.
- `frontend/src/pages/Audit.tsx` [advisory, 60%]: Every entry has a button with the same name, "Show raw". A screen-reader user tabbing through 50 entries hears 50 identical buttons with no way to tell which entry each one opens.
- `frontend/src/pages/Audit.test.tsx` [minor, 65%]: The date filter test only covers `date_from`. Nothing tests `date_to` or the "Action starts with" filter. Nothing tests that a filter change resets `offset` to 0. The paging buttons and the "No audit entries match these filters." empty state are also untested.

## Fixes Applied
- cycle 1: engineering-frontend-developer on F-001, F-002 (done); checks 19/19 passed
- minor findings: engineering-frontend-developer on F-003, F-004, F-005, F-009, F-010, F-011 (done); engineering-backend-architect on F-007, F-008 (partial); left as is: F-009 (raw entity type identifiers): not a bug here. The "Record type" options already use labels from `/audit/entity-types`. / F-009 ("Action starts with" raw-text filter): left as is. Changing it needs a design decision. / F-007: not fixed. Renaming `_bounds` and `_zone` to public names has to happen in backend/app/report_metrics.py, which is not in my writable list. It also touches the internal callers at lines 236 and 440-441. Other modules (scheduling.py, client_notices.py) define their own private `_zone`, so a shared public name needs a naming decision.; checks 19/19 passed, 4 file(s) changed

## Cycle Delta
- cycle 1: 2 must-fix, 0 suggestions, 10 deferred, 0 dropped (low confidence)
- cycle 2: 1 out-of-domain finding(s) filtered (engineering-frontend-developer on testing, owner design-ux-researcher); see .planning/logs/authority-decisions-2026-11-03.log
- cycle 2: 0 must-fix (resolved 2, new 0, unchanged 0), 0 suggestions, 2 deferred, 0 dropped (low confidence)

## Coverage
No coverage data found (looked for coverage/coverage-summary.json, coverage-summary.json, coverage/lcov.info, lcov.info, coverage.xml, coverage/cobertura-coverage.xml, coverage/coverage.xml, coverage.txt, coverage/coverage.txt). Advisory only: run the test suite with coverage to check review.coverage_thresholds.
