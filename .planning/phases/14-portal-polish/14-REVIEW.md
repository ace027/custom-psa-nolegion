# Phase 14: Portal polish — Review Summary

## Result: ESCALATED

**Cycles Used**: 3
**Reviewers**: testing-qa-verification-specialist, engineering-senior-developer, design-ux-researcher, engineering-backend-architect
**Evaluators**: code-quality, ui-ux, integration, business-logic
**Completed**: 2026-10-31

## Findings Summary
- Must-fix (blocker, critical, major) found: 6; fixed: 5; unresolved: 1
- Suggestions (minor, advisory): 6
- Deferred (confidence 50-79%): 24
- Hot spots (flagged by 2+ reviewers): `backend/app/portal_files.py`, `backend/app/routers/portal.py`, `backend/app/auth/oidc.py`, `backend/app/portal.py`, `frontend/src/portal/ExportButton.tsx`, `frontend/src/portal/PortalLogin.tsx`, `frontend/src/portal/PortalAttachments.tsx`, `frontend/src/portal/MyDetailsPage.tsx`, `backend/tests/test_portal_polish.py`, `frontend/src/portal/PortalApp.tsx`

## Findings Detail
| ID | Severity | Location | Issue | Reviewers | Confidence | Status |
|----|----------|----------|-------|-----------|------------|--------|
| F-001 | major | `backend/app/portal_files.py (with backend/app/portal_schemas.py):55-58` | The upload is a JSON body with `content_base64` and no `max_length`. I found no body-size limit in `app/` (grep for `max_body` and `content-length` found nothing). The `_decode` size check only runs after FastAPI and Pydantic have read and parsed the whole request into memory. The 10 MB cap is therefore not enforced before the memory is spent. | testing-qa-verification-specialist | 80% | fixed |
| F-002 | major | `frontend/src/portal/PortalApp.tsx:79-91` | `Verify` only shows the error card when `redeem.isError`. If the URL has no `#token` (a bare `/portal/verify`, a mangled link, or a reload after the fragment was stripped by `replaceState`), `redeem.mutate` is never called. The page then shows "Signing you in…" forever. | evaluator:ui-ux | 90% | fixed |
| F-003 | minor | `frontend/src/portal/PortalApp.tsx:107-114` | The portal nav now has 6 tabs, with `px-3.5` padding and no `flex-wrap` or `overflow-x-auto`. The `<nav>` has no `aria-label`. | evaluator:ui-ux | 80% | deferred |
| F-004 | major | `backend/app/portal_schemas.py (with backend/app/portal_files.py):16` | F-001 is only partly fixed. `max_length` on `content_base64` is applied by Pydantic after FastAPI has read the whole body and parsed the JSON, so memory is spent before the cap applies. I found no request-size limit in `app/`. The comment in `_decode` (line 57) says so itself: "the request-size limit itself is not enforced here". The field cap and the `_decode` pre-check are the same check, applied after parsing. | engineering-senior-developer | 85% | fixed |
| F-005 | major | `backend/app/portal_files.py (with backend/app/portal_schemas.py and backend/app/routers/portal.py):56-58` | F-001 is not fixed. The upload still takes a JSON body with a base64 string. The only changes are a `max_length` of about 14 MB on `content_base64` and a comment in `_decode` that says the request-size limit is not enforced. Pydantic checks `max_length` after FastAPI has read the whole body and parsed the JSON, so memory is spent before the cap applies. My grep of `backend/` found no body-size middleware and no Content-Length check; the only `content-length` hits were in `dev/fake_graph.py`. Any authenticated portal contact can POST a body of hundreds of MB, and many such requests can run in parallel. The 20-uploads-per-hour limit runs only after decoding, so it does not stop this. | engineering-backend-architect | 90% | fixed |
| F-006 | major | `frontend/src/portal/PortalApp.tsx:109-116` | The tab nav is `flex gap-1` with no wrapping or horizontal scroll. With 6 tabs (Tickets, Appointments, Invoices, Devices, Help articles, My details), it overflows a 320-390px viewport and clips or forces page-level horizontal scroll. The `<nav>` also has no `aria-label`. | evaluator:ui-ux | 80% | fixed |
| F-007 | minor | `frontend/src/portal/PortalApp.tsx:224-237` | The invoices table has 6 columns and no `overflow-x-auto` wrapper. `Devices` wraps its table in `overflow-x-auto` with `min-w-[34rem]`, so the two are inconsistent. The last `<th />` is empty with no accessible name. The `th` elements have no `scope`. | evaluator:ui-ux | 80% | deferred |
| F-008 | advisory | `frontend/src/portal/PortalApp.tsx:109` | F-006 is fixed. The nav now has `flex-wrap` and `aria-label="Portal sections"`, so the six tabs wrap instead of overflowing. `NavLink` also sets `aria-current="page"` on the active tab. No action needed. | design-ux-researcher, evaluator:ui-ux | 90% | deferred |
| F-009 | major | `frontend/src/portal/PortalApp.tsx:224-237` | The invoice list table has 6 columns, and the invoice detail table has 4 columns plus a `tfoot`. Neither is wrapped in `overflow-x-auto` or given a min width. `Devices` (lines 295-296) does both. | evaluator:ui-ux | 85% | open |
| F-010 | minor | `frontend/src/portal/PortalApp.tsx:157-160` | Each ticket row is `flex items-center justify-between` with no `flex-wrap`, `gap` or `min-w-0`. A long subject sits next to a long "status · date" span that can't shrink. | evaluator:ui-ux | 80% | deferred |
| F-011 | minor | `frontend/src/portal/PortalApp.tsx:58` | The loading text in `Gate` ("Loading…") has no `role="status"`. The "This link cannot be used" error card in `Verify` has no `role="alert"` or focus move. Only the "Signing you in…" message in `Verify` is announced. | evaluator:ui-ux | 80% | deferred |
| F-012 | minor | `frontend/src/portal/PortalApp.tsx:99-102` | The `logout` mutation has no error or pending handling. The Sign out button isn't disabled while the request runs, and a failed logout shows nothing. | evaluator:ui-ux | 80% | deferred |

## Unresolved Findings
| ID | Severity | Location | Issue | Reviewers | Confidence | Status |
|----|----------|----------|-------|-----------|------------|--------|
| F-009 | major | `frontend/src/portal/PortalApp.tsx:224-237` | The invoice list table has 6 columns, and the invoice detail table has 4 columns plus a `tfoot`. Neither is wrapped in `overflow-x-auto` or given a min width. `Devices` (lines 295-296) does both. | evaluator:ui-ux | 85% | open |

## Resolved Findings
| ID | Severity | Location | Issue | Reviewers | Confidence | Status |
|----|----------|----------|-------|-----------|------------|--------|
| F-001 | major | `backend/app/portal_files.py (with backend/app/portal_schemas.py):55-58` | The upload is a JSON body with `content_base64` and no `max_length`. I found no body-size limit in `app/` (grep for `max_body` and `content-length` found nothing). The `_decode` size check only runs after FastAPI and Pydantic have read and parsed the whole request into memory. The 10 MB cap is therefore not enforced before the memory is spent. | testing-qa-verification-specialist | 80% | fixed |
| F-002 | major | `frontend/src/portal/PortalApp.tsx:79-91` | `Verify` only shows the error card when `redeem.isError`. If the URL has no `#token` (a bare `/portal/verify`, a mangled link, or a reload after the fragment was stripped by `replaceState`), `redeem.mutate` is never called. The page then shows "Signing you in…" forever. | evaluator:ui-ux | 90% | fixed |
| F-003 | minor | `frontend/src/portal/PortalApp.tsx:107-114` | The portal nav now has 6 tabs, with `px-3.5` padding and no `flex-wrap` or `overflow-x-auto`. The `<nav>` has no `aria-label`. | evaluator:ui-ux | 80% | deferred |
| F-004 | major | `backend/app/portal_schemas.py (with backend/app/portal_files.py):16` | F-001 is only partly fixed. `max_length` on `content_base64` is applied by Pydantic after FastAPI has read the whole body and parsed the JSON, so memory is spent before the cap applies. I found no request-size limit in `app/`. The comment in `_decode` (line 57) says so itself: "the request-size limit itself is not enforced here". The field cap and the `_decode` pre-check are the same check, applied after parsing. | engineering-senior-developer | 85% | fixed |
| F-005 | major | `backend/app/portal_files.py (with backend/app/portal_schemas.py and backend/app/routers/portal.py):56-58` | F-001 is not fixed. The upload still takes a JSON body with a base64 string. The only changes are a `max_length` of about 14 MB on `content_base64` and a comment in `_decode` that says the request-size limit is not enforced. Pydantic checks `max_length` after FastAPI has read the whole body and parsed the JSON, so memory is spent before the cap applies. My grep of `backend/` found no body-size middleware and no Content-Length check; the only `content-length` hits were in `dev/fake_graph.py`. Any authenticated portal contact can POST a body of hundreds of MB, and many such requests can run in parallel. The 20-uploads-per-hour limit runs only after decoding, so it does not stop this. | engineering-backend-architect | 90% | fixed |
| F-006 | major | `frontend/src/portal/PortalApp.tsx:109-116` | The tab nav is `flex gap-1` with no wrapping or horizontal scroll. With 6 tabs (Tickets, Appointments, Invoices, Devices, Help articles, My details), it overflows a 320-390px viewport and clips or forces page-level horizontal scroll. The `<nav>` also has no `aria-label`. | evaluator:ui-ux | 80% | fixed |
| F-007 | minor | `frontend/src/portal/PortalApp.tsx:224-237` | The invoices table has 6 columns and no `overflow-x-auto` wrapper. `Devices` wraps its table in `overflow-x-auto` with `min-w-[34rem]`, so the two are inconsistent. The last `<th />` is empty with no accessible name. The `th` elements have no `scope`. | evaluator:ui-ux | 80% | deferred |
| F-008 | advisory | `frontend/src/portal/PortalApp.tsx:109` | F-006 is fixed. The nav now has `flex-wrap` and `aria-label="Portal sections"`, so the six tabs wrap instead of overflowing. `NavLink` also sets `aria-current="page"` on the active tab. No action needed. | design-ux-researcher, evaluator:ui-ux | 90% | deferred |
| F-010 | minor | `frontend/src/portal/PortalApp.tsx:157-160` | Each ticket row is `flex items-center justify-between` with no `flex-wrap`, `gap` or `min-w-0`. A long subject sits next to a long "status · date" span that can't shrink. | evaluator:ui-ux | 80% | deferred |
| F-011 | minor | `frontend/src/portal/PortalApp.tsx:58` | The loading text in `Gate` ("Loading…") has no `role="status"`. The "This link cannot be used" error card in `Verify` has no `role="alert"` or focus move. Only the "Signing you in…" message in `Verify` is announced. | evaluator:ui-ux | 80% | deferred |
| F-012 | minor | `frontend/src/portal/PortalApp.tsx:99-102` | The `logout` mutation has no error or pending handling. The Sign out button isn't disabled while the request runs, and a failed logout shows nothing. | evaluator:ui-ux | 80% | deferred |

## Recommendation
Fix the unresolved findings by hand, accept the phase as is, or investigate further.

## Reviewer Verdicts
- Cycle 1, testing-qa-verification-specialist: **NEEDS WORK**
- Cycle 1, engineering-senior-developer: **NEEDS WORK**
- Cycle 1, design-ux-researcher: **NEEDS WORK**
- Cycle 1, engineering-backend-architect: **PASS**
- Cycle 1, evaluator:code-quality: **NEEDS WORK**
- Cycle 1, evaluator:ui-ux: **NEEDS WORK**
- Cycle 1, evaluator:integration: **NEEDS WORK**
- Cycle 1, evaluator:business-logic: **NEEDS WORK**
- Cycle 2, testing-qa-verification-specialist: **NEEDS WORK**
- Cycle 2, engineering-senior-developer: **NEEDS WORK**
- Cycle 2, design-ux-researcher: **PASS**
- Cycle 2, engineering-backend-architect: **NEEDS WORK**
- Cycle 2, evaluator:ui-ux: **NEEDS WORK**
- Cycle 3, testing-qa-verification-specialist: **PASS**
- Cycle 3, engineering-senior-developer: **PASS**
- Cycle 3, design-ux-researcher: **PASS**
- Cycle 3, engineering-backend-architect: **PASS**
- Cycle 3, evaluator:ui-ux: **NEEDS WORK**

## Suggestions (Not Required)
- F-003 `frontend/src/portal/PortalApp.tsx`: The portal nav now has 6 tabs, with `px-3.5` padding and no `flex-wrap` or `overflow-x-auto`. The `<nav>` has no `aria-label`. (fix: Use `flex flex-wrap` or `overflow-x-auto` on the nav and add `aria-label="Portal sections"`.)
- F-007 `frontend/src/portal/PortalApp.tsx`: The invoices table has 6 columns and no `overflow-x-auto` wrapper. `Devices` wraps its table in `overflow-x-auto` with `min-w-[34rem]`, so the two are inconsistent. The last `<th />` is empty with no accessible name. The `th` elements have no `scope`. (fix: Wrap the table in `<div className="overflow-x-auto">` with a min width as in `Devices`. Use `<th scope="col">` and give the last header `<span className="sr-only">Status</span>`.)
- F-008 `frontend/src/portal/PortalApp.tsx`: F-006 is fixed. The nav now has `flex-wrap` and `aria-label="Portal sections"`, so the six tabs wrap instead of overflowing. `NavLink` also sets `aria-current="page"` on the active tab. No action needed. (fix: None.)
- F-010 `frontend/src/portal/PortalApp.tsx`: Each ticket row is `flex items-center justify-between` with no `flex-wrap`, `gap` or `min-w-0`. A long subject sits next to a long "status · date" span that can't shrink. (fix: Use `flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between`. Add `min-w-0 break-words` on the link and `shrink-0` on the status span.)
- F-011 `frontend/src/portal/PortalApp.tsx`: The loading text in `Gate` ("Loading…") has no `role="status"`. The "This link cannot be used" error card in `Verify` has no `role="alert"` or focus move. Only the "Signing you in…" message in `Verify` is announced. (fix: Add `role="status"` to the Gate loading paragraph. Wrap the failure message in `role="alert"`, or focus its heading on render.)
- F-012 `frontend/src/portal/PortalApp.tsx`: The `logout` mutation has no error or pending handling. The Sign out button isn't disabled while the request runs, and a failed logout shows nothing. (fix: Add `disabled={logout.isPending}` and render `<ErrorMsg error={logout.error} />` in the header or Shell. Add a visible `focus-visible` ring to the button.)

## Deferred (Medium Confidence)
- `backend/app/portal_files.py` [major, 60%]: A portal upload only stores the file and writes an audit row. Unlike `portal.reply`, it does not call `reopen_on_customer_activity`. It does not notify the assignee either, and it adds no ticket note or timeline entry.
- `backend/app/routers/portal.py` [minor, 70%]: The "create session, flush, audit, set cookie" sequence appears twice, in `verify` and in `sso_callback`. Each copy repeats the `max_age` and `_cookie_args()` arguments.
- `backend/app/auth/oidc.py` [advisory, 60%]: `PortalLoginDenied` is a copy of `LoginDenied` with an identical body.
- `backend/app/portal.py` [minor, 60%]: Each of the three `export_*` functions imports `to_csv` from `app.reports` inside the function body. `export_devices` redefines the column list that `list_devices` already fixes in its `keep` tuple. `export_invoices` and `export_devices` fetch the full list and then slice it to `EXPORT_MAX_ROWS` in Python.
- `backend/app/portal_files.py` [minor, 65%]: The file is written to disk before the DB transaction commits. Cleanup runs only if `flush()` fails. If `audit.record` or the later commit raises, the file stays on disk with no row pointing to it.
- `frontend/src/portal/ExportButton.tsx` [minor, 60%]: The CSV export is a bare `<a download>` link. The button has no pending state, no success message and no error handling. If the session has expired or the server returns 401, 403 or 5xx, the browser saves or shows a JSON error body, or does nothing.
- `frontend/src/portal/PortalLogin.tsx` [minor, 65%]: The "Sign in with Microsoft" button appears only after the `login-options` query resolves. There is no loading placeholder, so the layout shifts. A failed query silently hides SSO. Navigation is done through a `<button>` and `window.location.assign`.
- `frontend/src/portal/PortalAttachments.tsx` [minor, 60%]: There is no loading state for the attachment list, so a blank list shows until the data arrives. The file input is a bare `<input type="file">` with no `inputCls` styling and no visible focus treatment. `role="status"` and `role="alert"` paragraphs are rendered together with their content, which many screen readers do not announce reliably. Download links rely on colour and hover underline only.
- `frontend/src/portal/MyDetailsPage.tsx` [minor, 50%]: The form state is seeded from `me` once, with no reset or dirty tracking. A `PATCH` that returns trimmed or normalised values is not reflected back into the inputs. The Save button stays enabled when nothing has changed. The "Saved" message disappears on any keystroke, but the form has no "Discard" or "Reset" option. Phone and title have no format hints.
- `backend/app/routers/portal.py (with backend/app/portal_schemas.py)` [minor, 75%]: `PATCH /portal/me/contact` has PUT semantics. `name` is required, and an omitted `phone` or `title` defaults to None. `update_contact` then assigns those values unconditionally, so it clears them.
- `backend/app/portal_files.py` [minor, 60%]: `_decode` checks the size only after FastAPI and pydantic have parsed the whole JSON body into `content_base64`. The upload rate limit also runs after the full decode.
- `backend/app/routers/portal.py` [minor, 70%]: `except Exception: return deny("token_exchange")` swallows every failure with no logging. Config errors, a JWKS fetch failure and a programming error all appear as `token_exchange` in the audit event.
- `backend/app/portal_files.py, frontend/src/api.ts` [advisory, 60%]: The allowed-extension list and the 10 MB limit are hard-coded in both the backend and the frontend. The 10 MB value is a setting (`max_attachment_bytes`) on the backend.
- `backend/tests/test_portal_polish.py` [major, 70%]: Several stated or security-relevant paths have no test. By the test names: - **Same-org visibility:** an attachment uploaded by a contact without `portal_org_tickets` is not shown to or downloadable by a colleague in the same org who cannot see that ticket. - **Export cap:** `EXPORT_MAX_ROWS` is not exercised. - **Audit:** there is no test for the `portal.attachment_upload`, `portal.export` or `portal.contact_update` events. - **Download:** no test that the download response sets `Content-Disposition` or `nosniff`, or covers a missing file or path traversal. - **Extensions:** no uppercase-extension or double-extension case such as `a.exe.txt`.
- `backend/tests/test_portal_sso.py` [minor, 55%]: The SSO tests cover claims handling and the `iss` validator. By their names, none exercises the callback's state, nonce or PKCE failure paths: a mismatched `state`, a replayed callback, or a missing session. `test_token_exchange_failure_is_denied` mocks the exchange as a whole.
- `frontend/src/portal/MyDetailsPage.tsx` [minor, 55%]: The email-note paragraph is positioned outside `Field` with a `-mt-2` offset hack. The phone input has no `type="tel"`. The "Saved" `role="status"` is mounted together with its text. Form state is seeded once from `me`, so it goes stale if `me` changes. Failed validation, such as a blank name, only disables Save and gives no reason.
- `backend/app/auth/oidc.py` [major, 65%]: On a first sign-in the contact is matched by the `email` claim, and when that is absent by `preferred_username`. Microsoft documents `email` as unverified and mutable and `preferred_username` as display-only. Neither is a safe identifier for authorization or for first-time account binding. A test (`test_preferred_username_is_used_when_email_claim_is_absent`) locks this behaviour in.
- `frontend/src/api.ts, frontend/src/portal/PortalAttachments.tsx` [minor, 60%]: The client hard-codes the 10 MB limit and the extension list. The server's limit comes from the configurable `max_attachment_bytes`, and the extension list lives in a separate backend constant. Nothing links the two copies, and no test checks that they match.
- `backend/app/services.py` [minor, 55%]: Changing or clearing an organization's `entra_tenant_id` does not revoke that organization's contacts' portal sessions, and does not clear their bound `entra_oid`. The comment and docs say only that the tenant id "decides whose accounts reach the portal". Existing sessions from the old tenant stay valid until they expire (`portal_session_hours`).
- `frontend/src/portal/PortalApp.tsx` [minor, 70%]: The error card gives one message, "It has expired or was already used", for three cases: a missing token, an expired or used token, and a network or server error. The card has no `role="alert"`. The "Signing you in…" status is replaced without announcing the failure.
- `frontend/src/portal/PortalApp.tsx` [minor, 60%]: The loading states are inconsistent. `Gate` shows a bare `<p>Loading…</p>` with no `role="status"`. The Tickets, Invoices and TicketPage lists render nothing while loading, so there is no skeleton or text. Invoices shows "No invoices yet." only after the data loads, with no loading text before that. `Gate` and `Verify` have no retry on error.
- `backend/app/portal_files.py` [minor, 60%]: The error messages ("That file is too large", "That file type is not allowed") don't tell the user the size limit or the allowed types. The 429 message gives no retry time.
- `backend/app/portal_files.py` [advisory, 50%]: The upload still decodes and holds the whole file in memory (at most about 14 MB of body, plus the decoded copy) before the hourly-limit query runs. The 20 per hour limit is checked after decoding. The 413 body cap now bounds this, so F-004 and F-005 are fixed. Per-request memory is bounded, but concurrent uploads from one contact are not throttled until after decode.
- `backend/app/portal_files.py` [advisory, 55%]: F-004, F-005 and F-006 are fixed. `SizeLimitedRoute` is attached to the upload route through `route_class_override` at routers/portal.py:376. It rejects a body with 413 on an oversized Content-Length and counts streamed bytes for chunked bodies. `test_oversized_body_is_rejected_before_parsing` covers both paths. In PortalApp.tsx the nav (line 109) now has `flex-wrap` and `aria-label="Portal sections"`. One gap remains. FastAPI reads the body before it resolves dependencies, so an unauthenticated caller can still make the server buffer up to about 14 MB per request (with the default cap) before the auth check returns 401. The cost is bounded per request and no worse than any other endpoint.

## Fixes Applied
- cycle 1: engineering-senior-developer on F-001 (partial); engineering-frontend-developer on F-002 (done); checks 11/15 passed
- cycle 2: engineering-senior-developer on F-004, F-005 (done); engineering-frontend-developer on F-006 (done); checks 15/15 passed

## Cycle Delta
- cycle 1: 2 out-of-domain finding(s) filtered (testing-qa-verification-specialist on database, owner engineering-backend-architect; testing-qa-verification-specialist on database, owner engineering-backend-architect); see .planning/logs/authority-decisions-2026-10-31.log
- cycle 1: 2 must-fix, 1 suggestions, 19 deferred, 0 dropped (low confidence)
- cycle 2: 2 out-of-domain finding(s) filtered (testing-qa-verification-specialist on backend, owner engineering-backend-architect; engineering-senior-developer on api-design, owner engineering-backend-architect); see .planning/logs/authority-decisions-2026-10-31.log
- cycle 2: 3 must-fix (resolved 2, new 3, unchanged 0), 1 suggestions, 3 deferred, 0 dropped (low confidence)
- cycle 3: 1 must-fix (resolved 3, new 1, unchanged 0), 4 suggestions, 2 deferred, 0 dropped (low confidence)

## Coverage
No coverage data found (looked for coverage/coverage-summary.json, coverage-summary.json, coverage/lcov.info, lcov.info, coverage.xml, coverage/cobertura-coverage.xml, coverage/coverage.xml, coverage.txt, coverage/coverage.txt). Advisory only: run the test suite with coverage to check review.coverage_thresholds.
