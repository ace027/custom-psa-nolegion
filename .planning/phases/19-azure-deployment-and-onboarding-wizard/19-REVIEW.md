# Phase 19: Azure deployment and onboarding wizard — Review Summary

## Result: PASSED

**Cycles Used**: 2
**Reviewers**: testing-qa-verification-specialist, engineering-senior-developer, engineering-backend-architect, design-ux-researcher
**Evaluators**: code-quality, ui-ux, integration, business-logic
**Completed**: 2026-11-03

## Findings Summary
- Must-fix (blocker, critical, major) found: 3; fixed: 3; unresolved: 0
- Suggestions (minor, advisory): 2
- Deferred (confidence 50-79%): 20
- Hot spots (flagged by 2+ reviewers): `backend/app/onboarding.py`, `backend/app/keyvault.py`, `deploy/azure/deploy.sh`, `deploy/azure/main.bicep`, `frontend/src/pages/admin/Setup.tsx`, `docs/AZURE_DEPLOY.md`

## Findings Detail
| ID | Severity | Location | Issue | Reviewers | Confidence | Status |
|----|----------|----------|-------|-----------|------------|--------|
| F-001 | major | `deploy/azure/main.bicep:144-153` | The same managed identity is attached to the internet-facing api and to worker, and it holds Key Vault Secrets Officer on the whole vault. That role gives read, write and delete on every secret. Those include `pg-admin-password`, `migration-database-url` (the owner DB credential), `credentials-key`, `session-secret` and `entra-client-secret`. The api only needs write access to six wizard-managed secrets. The comment calls this an "accepted risk", but the criterion requires no unresolved HIGH findings. | engineering-backend-architect, evaluator:integration, evaluator:business-logic | 80% | fixed |
| F-002 | critical | `deploy/azure/deploy.sh:81-96` | The staff sign-in app is created and updated with only the `/api/v1/auth/callback` redirect URI. The wizard's consent flow (backend/app/onboarding_auth.py:51-52) sends `redirect_uri=${public_url}/api/v1/onboarding/consent/callback`. No file under deploy/ or docs/ registers that URI on the staff app (a grep for `consent/callback` finds only code and tests). | evaluator:code-quality | 85% | fixed |
| F-003 | blocker | `deploy/azure/deploy.sh (also docs/AZURE_DEPLOY.md line 12, docs/ENTRA_SETUP.md):64` | `onboarding_auth._redirect_uri()` sends the admin consent flow to `{PUBLIC_URL}/api/v1/onboarding/consent/callback` on the staff app. deploy.sh registers only `/api/v1/auth/callback`. No doc or script registers the consent URI. Every `az ad app update` re-run also resets the redirect list to that single URI. | evaluator:integration | 90% | fixed |
| F-004 | advisory | `none` | PASS. I re-checked F-001, F-002 and F-003 against the files and found no defect. | testing-qa-verification-specialist | 80% | deferred |
| F-005 | minor | `docs/AZURE_DEPLOY.md:14` | The table says the managed identity has "Key Vault Secrets User + Secrets Officer on the vault". The template now grants Secrets Officer only on six named secrets (main.bicep lines 144-168). The document does not say which six. | design-ux-researcher, evaluator:integration | 90% | deferred |

## Reviewer Verdicts
- Cycle 1, testing-qa-verification-specialist: **NEEDS WORK**
- Cycle 1, engineering-senior-developer: **PASS**
- Cycle 1, engineering-backend-architect: **PASS**
- Cycle 1, design-ux-researcher: **NEEDS WORK**
- Cycle 1, evaluator:code-quality: **NEEDS WORK**
- Cycle 1, evaluator:ui-ux: **NEEDS WORK**
- Cycle 1, evaluator:integration: **NEEDS WORK**
- Cycle 1, evaluator:business-logic: **NEEDS WORK**
- Cycle 2, testing-qa-verification-specialist: **PASS**
- Cycle 2, engineering-senior-developer: **PASS**
- Cycle 2, engineering-backend-architect: **NEEDS WORK**
- Cycle 2, design-ux-researcher: **PASS**
- Cycle 2, evaluator:code-quality: **PASS**
- Cycle 2, evaluator:integration: **NEEDS WORK**

## Suggestions (Not Required)
- F-004 `none`: PASS. I re-checked F-001, F-002 and F-003 against the files and found no defect. (fix: none.)
- F-005 `docs/AZURE_DEPLOY.md`: The table says the managed identity has "Key Vault Secrets User + Secrets Officer on the vault". The template now grants Secrets Officer only on six named secrets (main.bicep lines 144-168). The document does not say which six. (fix: Change the line to "Key Vault Secrets User on the vault; Secrets Officer only on the six wizard-managed secrets (list them); AcrPull on the registry". Update it again if Finding 1 is fixed.)

## Deferred (Medium Confidence)
- `backend/app/onboarding.py` [major, 60%]: `_create_app` posts `/applications`, then immediately posts `/servicePrincipals`. `_new_secret_to_vault` then posts `addPassword` on the new app. Entra replicates new apps with a delay, so these follow-up calls often fail with 400 or 404 in the first seconds. There is no retry. A failure raises a 502, and the app already exists in the tenant. The retry then gets a 409 `AppExists`, which tells the admin to "connect it instead". The admin sees a failed create followed by a confusing 409. For the mail app, the Exchange `powershell` output is only returned on a successful create.
- `backend/app/onboarding.py` [minor, 60%]: The "outside scope" probe reads `ctx.user.email`'s inbox and expects 403. If the admin signs in with the support mailbox address itself, the probe returns 200. The wizard then reports "The mail app can read mailboxes outside its scope", which is false. If the admin has no Exchange mailbox, the probe returns 404 or similar and the wizard reports "Could not check the mailbox scope".
- `backend/app/keyvault.py` [minor, 70%]: `r.json()` and `body["access_token"]` run on a 200 response from the identity endpoint with no guard. A non-JSON body raises `ValueError`, and a missing key raises `KeyError`. Neither is a `KeyVaultError`, so both escape the wizard's `except KeyVaultError` handlers as a 500. In `_not_running`, the exception would crash the whole `/status` call.
- `deploy/azure/deploy.sh` [minor, 65%]: Under `set -e`, a single transient failure of `az containerapp job execution show` inside the polling loop assigns nothing and aborts the whole script. This happens right after infrastructure deploy, while the migration is running. The re-run is safe, but an `az` throttle or network blip kills the deploy mid-migration.
- `backend/app/onboarding.py` [minor, 70%]: `_mail_status` calls `client._request_user`, a private method of `GraphClient` in `app/mail/graph.py:201`. It also relies on `GraphError.status` being None for network and sign-in failures.
- `backend/app/onboarding.py` [minor, 60%]: `_differences(kind, app, token)` is one function with two unrelated bodies. The mail branch never uses `token`, and the portal branch is the only one that makes a Graph call (`_portal_scope_ids(token)`).
- `backend/app/onboarding.py, backend/app/onboarding_auth.py` [minor, 55%]: Both modules define a near-identical `_http_client()` that returns `httpx.Client(follow_redirects=False)`. Only the timeout differs (30 vs 15). Neither uses the shared client or timeout setting that `keyvault.py` and the mail code use.
- `backend/app/keyvault.py` [minor, 60%]: `KeyVault.from_settings()` builds a new instance on every call. The managed-identity token is cached on the instance (`self._token`), so the cache is discarded each time. During one `verify`, `_not_running` runs up to 3 times and each run fetches a new token plus a new `httpx.Client`. The clients are never closed.
- `frontend/src/pages/admin/Setup.tsx` [major, 70%]: Step 2 consent state is shown only through the one-time `?consent=ok` query param. After a reload, or when the admin arrives without it, nothing shows whether Microsoft consent was already granted. The Create and Connect buttons in steps 3 and 4 are always enabled. An admin who skips step 2, or whose stored token has expired, clicks Create and gets a raw backend error from `ErrorMsg`. The status list has no consent step to say what to do next.
- `frontend/src/pages/admin/Setup.tsx` [major, 75%]: Neither the create nor the connect mutation shows any success message. The only success feedback is a status badge that changes after a refetch. A badge change is not announced, and the status and verify regions have no `aria-live`. Nothing indicates that a refetch is in progress, and there is no loading state for the initial status query (`status.isLoading`). The Copy button gives no confirmation, and the clipboard write failure is swallowed (`void`).
- `frontend/src/pages/admin/Setup.tsx` [minor, 65%]: The restart step says "az containerapp revision restart (see your deployment notes)" with no resource names or link. Finish is always enabled, even when steps are missing, in error, or waiting for a restart. Its confirm text does not mention unfinished steps.
- `frontend/src/nav/navConfig.ts (line 119) and frontend/src/App.tsx (line 279)` [minor, 70%]: The Setup nav entry is gated on `permission: "user:manage"`. The `/setup` route is gated on `config:manage` and `me.role === "admin"`. The backend guard is admin role plus `CONFIG_MANAGE`.
- `backend/app/routers/onboarding.py` [minor, 55%]: The `error` branch of the consent callback pops the pending consent state without checking `state`. It also writes an audit row containing the attacker-controlled `error` value (truncated to 100 characters).
- `frontend/src/pages/admin/Setup.tsx` [advisory, 50%]: Colours are hard-coded Tailwind palette classes (`bg-green-100 text-green-800`, `bg-slate-900` and similar). The error block at line 124 is inline markup instead of the shared `ErrorMsg`. The badge is a bare `span` rather than a shared component.
- `frontend/src/pages/admin/Setup.tsx` [minor, 55%]: Finish uses a blocking `window.confirm`. The Restart step tells the user to run a generic `az containerapp revision restart` command with no resource names and no copyable command. Finish stays enabled while steps are still `missing` or `error`, and the user gets no warning.
- `backend/app/onboarding.py` [minor, 60%]: When the admin token is available, portal verification checks only that the app exists and has the redirect URI. It does not check the sign-in audience, the permissions, or that the stored secret is valid. When there is no token it reports "ok" from config alone.
- `frontend/src/nav/navConfig.ts` [minor, 60%]: The Setup nav entry is gated on `user:manage`. The route in App.tsx:279 and the API require `config:manage` plus the admin role.
- `backend/app/onboarding.py` [major, 75%]: The wizard never creates or connects the staff SSO app. `verify()` reports `staff_sso` "ok" whenever `s.entra_configured` is true, which only checks that three settings are non-empty. It does not call Graph to confirm the app exists, has the redirect URI `/api/v1/auth/callback`, or has a valid secret. Step 1 in Setup.tsx 119-121 only says "You are signed in, so staff sign-in works."
- `backend/app/onboarding.py` [major, 70%]: `finish()` starts with `get_admin_token`, which raises 409 once the one-time token has expired (at most 60 minutes). An admin who comes back later cannot revoke anything without re-consenting. If they never click Finish, the three directory-wide delegated grants (Application.ReadWrite.All, AppRoleAssignment.ReadWrite.All, DelegatedPermissionGrant.ReadWrite.All) stay on the staff app indefinitely. Only the local ciphertext is deleted at expiry.
- `deploy/azure/main.bicep` [major, 70%]: F-001 is fixed for writes. Write access is now scoped to the six wizard secrets. The one user-assigned identity is still attached to the internet-reachable api, the worker, the proxy and the migrate job. It holds Key Vault Secrets User on the whole vault (`kvSecretsUser`). Anyone who gets code execution in the api container, for example through SSRF to the managed-identity token endpoint, can read `migration-database-url` and `pg-admin-password`. Those are the owner credentials for the PostgreSQL server. The runtime role `psa_app` is subject to RLS. The owner role is not, so these credentials bypass RLS entirely.

## Fixes Applied
- cycle 1: engineering-senior-developer on F-001, F-002, F-003 (partial); checks 22/22 passed
- minor findings: engineering-senior-developer on F-005, F-004 (done); engineering-backend-architect on F-001, F-002, F-003, F-005, F-006, F-008 (partial); left as is: F-001: skipped. Retrying with sleeps and making a 409 on `create_*` fall through to connect are design decisions, and the finding rated it major. / F-005: skipped. It needs a new public `GraphClient.probe` in `backend/app/mail/graph.py`, which is not in my writable files.; checks 22/22 passed, 5 file(s) changed

## Cycle Delta
- cycle 1: 3 must-fix, 0 suggestions, 19 deferred, 0 dropped (low confidence)
- cycle 2: 0 must-fix (resolved 3, new 0, unchanged 0), 2 suggestions, 1 deferred, 0 dropped (low confidence)

## Coverage
No coverage data found (looked for coverage/coverage-summary.json, coverage-summary.json, coverage/lcov.info, lcov.info, coverage.xml, coverage/cobertura-coverage.xml, coverage/coverage.xml, coverage.txt, coverage/coverage.txt). Advisory only: run the test suite with coverage to check review.coverage_thresholds.

## Security Review

**Verdict**: PASS — 0 unresolved CRITICAL/HIGH finding(s). Details: `SECURITY-REVIEW.md`.
