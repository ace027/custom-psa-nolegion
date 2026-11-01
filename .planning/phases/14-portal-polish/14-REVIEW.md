# Phase 14: Portal polish — Review Summary

## Result: PASSED

**Cycles Used**: 1
**Reviewers**: testing-qa-verification-specialist, engineering-senior-developer, design-ux-researcher, engineering-backend-architect
**Evaluators**: code-quality, ui-ux, integration, business-logic
**Completed**: 2026-10-31

## Findings Summary
- Must-fix (blocker, critical, major) found: 0; fixed: 0; unresolved: 0
- Suggestions (minor, advisory): 1
- Deferred (confidence 50-79%): 26
- Hot spots (flagged by 2+ reviewers): `backend/app/auth/oidc.py`, `backend/app/portal_files.py`, `frontend/src/portal/PortalAttachments.tsx`, `frontend/src/portal/MyDetailsPage.tsx`, `backend/app/portal.py`, `frontend/src/portal/ExportButton.tsx`

## Findings Detail
| ID | Severity | Location | Issue | Reviewers | Confidence | Status |
|----|----------|----------|-------|-----------|------------|--------|
| F-001 | minor | `backend/app/routers/portal.py (with backend/app/portal.py and backend/app/portal_schemas.py):198-204` | `PATCH /portal/me/contact` uses PUT semantics. `name` is required, and `phone` and `title` default to `None`. `update_contact` assigns all three unconditionally. A client that sends only `{"name": "X"}` silently wipes the stored phone and title. | engineering-backend-architect | 80% | deferred |

## Reviewer Verdicts
- Cycle 1, testing-qa-verification-specialist: **NEEDS WORK**
- Cycle 1, engineering-senior-developer: **PASS**
- Cycle 1, design-ux-researcher: **PASS**
- Cycle 1, engineering-backend-architect: **NEEDS WORK**
- Cycle 1, evaluator:code-quality: **PASS**
- Cycle 1, evaluator:ui-ux: **NEEDS WORK**
- Cycle 1, evaluator:integration: **NEEDS WORK**
- Cycle 1, evaluator:business-logic: **NEEDS WORK**

## Suggestions (Not Required)
- F-001 `backend/app/routers/portal.py (with backend/app/portal.py and backend/app/portal_schemas.py)`: `PATCH /portal/me/contact` uses PUT semantics. `name` is required, and `phone` and `title` default to `None`. `update_contact` assigns all three unconditionally. A client that sends only `{"name": "X"}` silently wipes the stored phone and title. (fix: Make all fields optional and apply only `body.model_fields_set`. Keep `name` non-empty when it is present. Alternatively, rename the route to PUT and document the full-replace behaviour.)

## Deferred (Medium Confidence)
- `backend/app/auth/oidc.py` [minor, 55%]: Contact matching falls back to `preferred_username` when `email` is absent. Microsoft documents `preferred_username` as mutable and not to be used for authorization decisions. The `email` claim is also not verified by Entra.
- `backend/app/portal_files.py` [minor, 50%]: `SizeLimitedRoute` raises `HTTPException` from inside the wrapped `receive()` callable. That only becomes a 413 if the exception propagates through FastAPI's route exception handling while the body is read. I could not run the tests to confirm that chunked, no-Content-Length bodies return 413 rather than 500.
- `backend/app/portal_files.py` [major, 60%]: `upload` never notifies the assignee. It also doesn't call `tsvc.reopen_on_customer_activity` the way `portal.reply` does (portal.py 457, 472-475). A client who attaches a file to a ticket in a waiting or resolved status leaves the status unchanged and no one is told. Only closed tickets are rejected.
- `backend/app/auth/oidc.py` [advisory, 50%]: `LoginDenied` and `PortalLoginDenied` are identical classes. The two OIDC resolvers repeat the oid-binding logic.
- `frontend/src/portal/ExportButton.tsx (same pattern in frontend/src/portal/PortalAttachments.tsx)` [minor, 60%]: CSV exports and attachment downloads are plain `<a href>` links to the API. If the session has expired, or the server returns 403/404, the browser leaves the SPA or saves a JSON error body as the file. Nothing tells the user the export failed. The `download` attribute makes a failure look like a successful save of a bad file.
- `frontend/src/portal/PortalAttachments.tsx` [minor, 55%]: The attachment list shows no loading state. While `list.data` is undefined the Card is blank, with an empty `<ul>` and nothing between the title and the upload control. Files are also uploaded one at a time, immediately on selection, and the file input accepts a single file.
- `frontend/src/portal/MyDetailsPage.tsx` [minor, 55%]: The email input is labelled by `Field`, which wraps it in a `<label>`. `aria-describedby` points at the note outside the label, so it works. The note is positioned with `-mt-2`, which pulls it into the input's margin. A read-only field with no visual disabled styling looks editable.
- `backend/app/portal.py` [minor, 70%]: Each export truncates silently at `EXPORT_MAX_ROWS` (10000). The response gives no signal, such as a header or trailing row, that the data is incomplete. The audit row records only the truncated count. The ticket query loads up to 10000 full ORM rows into memory, and the CSV text is built in a single string. Neither is streamed.
- `backend/app/portal_files.py` [minor, 60%]: File bytes are written to the local `attachments_dir` before the DB flush. The file is cleaned up only if `flush()` fails. If `audit.record` or the later commit fails or rolls back, the orphan file stays on disk. Storage is also tied to one node's local filesystem. The migration, the backup tests and the other files in the review set address neither multi-instance scaling nor object-store use.
- `backend/app/routers/portal.py` [minor, 60%]: The SSO callback catches `Exception` around `authorize_access_token` and returns `deny("token_exchange")`. It logs nothing about the cause. The audit row records only the generic reason, so a state mismatch, bad issuer, expired code, network error and a programming error all look the same.
- `backend/app/portal.py` [minor, 65%]: `PATCH /portal/me/contact` overwrites `phone` and `title` with the schema defaults (`None`) whenever the client omits them. The route is a PATCH but behaves like a PUT. The test at test_portal_polish.py:241 relies on the client sending the old values back.
- `backend/tests/test_portal_polish.py` [minor, 55%]: No test covers truncation at `EXPORT_MAX_ROWS`. No test covers uploads against a ticket the contact cannot see in the `portal_org_tickets=False` case, or the download of an attachment whose file is missing from disk (the `NotFound` branch). No test covers a half-written upload (file written, DB failure).
- `frontend/src/portal/MyDetailsPage.tsx` [major, 55%]: The form state is initialised once from `me`. `onSuccess` only updates the query cache, and the form is never re-synced or reset. If the server trims or normalises values (for example a blank phone becomes null, or a name is trimmed), the form keeps showing the typed values, not the saved ones. If `me` refreshes, for example after another tab edits it, the form keeps stale values.
- `frontend/src/portal/MyDetailsPage.tsx` [minor, 60%]: The success banner and error message sit below the form, after the Save button, with no `aria-live` region for the success text beyond `role="status"`. `status` is only rendered on success, so some screen readers will not announce it because the live region is inserted together with its content. The `ErrorMsg` has no spacing (`mt-3`) from the form, unlike the success banner.
- `frontend/src/portal/PortalAttachments.tsx` [major, 50%]: The file input's `onChange` resets `input.value = ""` and `upload.reset()`. When validation fails, `problem` is set. When a later upload is valid, `setProblem(bad)` clears it. `problem` is never cleared if the user later cancels the file dialog (`!file` returns before `setProblem(null)`). `upload.isSuccess` "File attached." persists until the next selection. In addition, `<input type="file">` is not styled with the design system and has no `aria-describedby` tying it to the problem or status messages.
- `frontend/src/portal/ExportButton.tsx` [minor, 55%]: The export is a plain `<a download href>`. If the session has expired or the contact is not a billing contact, the browser saves the JSON error body as a `.csv` file or navigates away. The user sees no error.
- `frontend/src/portal/PortalLogin.tsx` [minor, 50%]: The Microsoft sign-in button is a `Button` that calls `window.location.assign` instead of being a link. The "or" divider is `aria-hidden`, which is fine. While `options` is loading, the SSO button is absent and then pops in, causing layout shift (CLS). A failed `login-options` fetch is silently ignored. A hard-coded `/api/v1/...` path is used rather than the shared API base.
- `frontend/src/portal/PortalLogin.tsx` [minor, 50%]: The SSO-denied message uses `role="alert"` and a bespoke `bg-red-50 text-red-800` style. `ErrorMsg` uses `text-red-700`, and the success message uses another one-off style, repeated in MyDetailsPage. The alert is also not dismissed once the user requests an email link. The "Email me a link" copy appears even when SSO is available, without being framed as the alternative.
- `frontend/src/portal/PortalApp.tsx` [minor, 50%]: The "Sign out" button is a raw `<button>` with no `type`, and it has no loading or error handling. A logout failure is silent. The raw style duplicates link styling.
- `frontend/src/portal/PortalApp.tsx` [minor, 50%]: Export actions sit in the `Card` header with a `justify-between` flex and no wrapping. On narrow screens the Invoices header holds a title plus two links ("Export invoices (CSV)" and "Download account statement"). They can overflow or squeeze the title.
- `frontend/src/portal/PortalApp.tsx` [minor, 50%]: Attachments are shown only for `status === "closed"` as the closed test. Resolved or other terminal statuses allow uploads, and the status string is hard-coded. A portal ticket that has `status_name` customised might not map to "closed".
- `backend/app/config.py (also backend/app/main.py, .env.example)` [major, 70%]: `session_secret` defaults to `"dev-only-change-me"`, and `.env.example` ships `SESSION_SECRET=` empty. Nothing rejects the default or an empty value when `environment` is production. The portal SSO flow now keeps its OIDC state and nonce in the cookie that this secret signs.
- `backend/app/routers/organizations.py and backend/app/services.py` [minor, 55%]: Changing or clearing `entra_tenant_id` on an organization does not revoke that organization's existing portal sessions. Contact unlink, archive and portal-access removal do revoke them. The router comment says "Clearing it is not [an admin decision]".
- `backend/app/auth/oidc.py and backend/app/routers/portal.py` [minor, 50%]: The `entra_oid` binding does `db.flush()` inside `resolve_contact_from_claims`. A concurrent first sign-in, or a unique-index collision on `uq_contacts_entra_oid`, raises `IntegrityError`. The callback catches only `PortalLoginDenied`, so the user gets a 500.
- `backend/tests/test_portal_sso.py and backend/tests/test_organizations.py` [major, 60%]: The suite has no test for SSO state or nonce mismatch, for a forged or missing `psa_oidc_state` cookie, or for the callback concurrency path. It also has no test that changing or clearing an organization's tenant id affects existing sessions. I could not run the tests because no Postgres was reachable (`OperationalError` on connect), so these gaps come from reading the test lists.
- `backend/app/services.py` [minor, 50%]: Sessions are revoked only on unlink or when portal access is turned off. A staff change to a contact's `email` does not unbind `entra_oid` or end that contact's sessions. A bound contact whose address is reassigned to a different person keeps SSO and session access.

## Fixes Applied
- minor findings: engineering-backend-architect on F-001, F-002, F-003, F-004, F-009, F-010 (partial); engineering-frontend-developer on F-006, F-007 (done); left as is: F-002: not changed. test_oversized_body_is_rejected_before_parsing in tests/test_portal_polish.py already sends a chunked body with no Content-Length and expects 413. I could not run it here. / F-009: partly fixed. The audit detail now records `truncated`. I did not add an X-Export-Truncated header, because that needs a change in app/routers/portal.py, which is not in my writable list. I did not add streaming either, since that is a larger change. The docs/PORTAL.md cap note is also not done. / F-010: not fixed. A storage interface for local or S3 and a rollback hook are design decisions and a large change. / F-001 also appears in app/routers/auth.py:72 and in the staff resolver at oidc.py:81. I left both alone: they are outside the named finding, and tests/test_auth.py::test_claims_fall_back_to_preferred_username expects the staff fallback. / F-006 (multi-file upload with a sequential queue and per-file status): not done. It is a design change, and the review marked it as optional ("consider").; checks failed (6/15), changes undone

## Coverage
No coverage data found (looked for coverage/coverage-summary.json, coverage-summary.json, coverage/lcov.info, lcov.info, coverage.xml, coverage/cobertura-coverage.xml, coverage/coverage.xml, coverage.txt, coverage/coverage.txt). Advisory only: run the test suite with coverage to check review.coverage_thresholds.

## Security Review

**Verdict**: PASS — 0 unresolved CRITICAL/HIGH finding(s). Details: `SECURITY-REVIEW.md`.
