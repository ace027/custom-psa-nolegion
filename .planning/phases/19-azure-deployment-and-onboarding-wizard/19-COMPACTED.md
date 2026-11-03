---
phase: 19-azure-deployment-and-onboarding-wizard
compacted: 2026-11-03
original_summaries: [19-01-SUMMARY.md, 19-02-SUMMARY.md, 19-03-SUMMARY.md, 19-04-SUMMARY.md]
requirements_satisfied: [R19-1, R19-2, R19-3]
---

# Phase 19: Azure deployment and onboarding wizard — Compacted Summary

## Deliverables
- 19-01 Azure deployment: Bicep, deploy script and guide (Complete with Warnings): deploy/azure/deploy.sh, deploy/azure/main.bicep, deploy/azure/main.parameters.example.json, docs/AZURE_DEPLOY.md, docs/ENTRA_SETUP.md
- 19-02 Key Vault writer, consent flow and bootstrap admin (backend) (Complete with Warnings): backend/alembic/versions/0043_onboarding_tokens.py, backend/app/bootstrap_admin.py, backend/app/config.py, backend/app/keyvault.py, backend/app/main.py, backend/app/models.py, backend/app/onboarding_auth.py, backend/app/routers/onboarding.py, backend/tests/test_bootstrap_admin.py, backend/tests/test_keyvault.py, backend/tests/test_onboarding_auth.py, backend/tests/test_seed_and_migrations.py, docs/api/openapi.json
- 19-03 Wizard steps: create, connect and verify registrations (backend) (Complete with Warnings): backend/app/onboarding.py, backend/app/routers/onboarding.py, backend/app/schemas.py, backend/tests/test_onboarding.py, docs/api/openapi.json
- 19-04 Setup wizard page (frontend) (Complete): frontend/src/nav/navConfig.ts

## Decisions
- 19-01: deploy.sh creates the Key Vault and ACR before Bicep (the secrets must exist before Bicep references them, and the images must be built before apps deploy). Bic
- 19-01: Names come from a 6-hex suffix (sha256 of subscription/resource group), passed to Bicep as `suffix`. That way deploy.sh knows the PG host and can build database
- 19-01: Two-pass deploy: Bicep `deployApps=false`, then the migrate job, then `deployApps=true`. Migrations run before new app code, and the first deploy does not fail 
- 19-02: The plan gave `start(ctx)` and `callback(ctx, code, state)`, but `Ctx` holds no request and deps.py is not in my file list. So they take the session as an argum
- 19-03: OnboardingError is a subclass of HTTPException, so main.py did not need a new handler; Graph 401 -> 409 "Sign in to Microsoft again"; other Graph or Key Vault f
- 19-04: The nav item uses the existing "cog" icon rather than a new one.

## Conventions and Open Questions
- 19-01 convention: The Bicep sets env vars KEY_VAULT_URL, AZURE_CLIENT_ID and ONBOARDING_ENABLED=true
- 19-01 convention: the wizard-managed secrets start as `unset`. This matches what 19-02's config.py now expects.
- 19-01 convention: Key Vault secret names the wizard (19-03) writes: portal-entra-client-id, portal-entra-client-secret, graph-tenant-id, graph-client-id, graph-client-secret, mai
- 19-02 convention: 19-01 deploy needs to run `python -m app.bootstrap_admin` in the migrate job with BOOTSTRAP_ADMIN_EMAIL and MIGRATION_DATABASE_URL, and set ONBOARDING_ENABLED, 
- 19-03 convention: Frontend: a 409 from POST /portal-app or /mail-app has the body {detail, app_id}
- 19-03 convention: offer "connect" using that app_id
- 19-04 convention: Setup.tsx does not read `app_id` from a 409 response, because the `api()` helper keeps only the message. The user types the existing app id into the "Use an exi

## Files Modified
| File | Change |
|------|--------|
| `deploy/azure/deploy.sh` | 19-01: Azure deployment: Bicep, deploy script and guide |
| `deploy/azure/main.bicep` | 19-01: Azure deployment: Bicep, deploy script and guide |
| `deploy/azure/main.parameters.example.json` | 19-01: Azure deployment: Bicep, deploy script and guide |
| `docs/AZURE_DEPLOY.md` | 19-01: Azure deployment: Bicep, deploy script and guide |
| `docs/ENTRA_SETUP.md` | 19-01: Azure deployment: Bicep, deploy script and guide |
| `backend/alembic/versions/0043_onboarding_tokens.py` | 19-02: Key Vault writer, consent flow and bootstrap admin (backend) |
| `backend/app/bootstrap_admin.py` | 19-02: Key Vault writer, consent flow and bootstrap admin (backend) |
| `backend/app/config.py` | 19-02: Key Vault writer, consent flow and bootstrap admin (backend) |
| `backend/app/keyvault.py` | 19-02: Key Vault writer, consent flow and bootstrap admin (backend) |
| `backend/app/main.py` | 19-02: Key Vault writer, consent flow and bootstrap admin (backend) |
| `backend/app/models.py` | 19-02: Key Vault writer, consent flow and bootstrap admin (backend) |
| `backend/app/onboarding_auth.py` | 19-02: Key Vault writer, consent flow and bootstrap admin (backend) |
| `backend/app/routers/onboarding.py` | 19-02: Key Vault writer, consent flow and bootstrap admin (backend) |
| `backend/tests/test_bootstrap_admin.py` | 19-02: Key Vault writer, consent flow and bootstrap admin (backend) |
| `backend/tests/test_keyvault.py` | 19-02: Key Vault writer, consent flow and bootstrap admin (backend) |
| `backend/tests/test_onboarding_auth.py` | 19-02: Key Vault writer, consent flow and bootstrap admin (backend) |
| `backend/tests/test_seed_and_migrations.py` | 19-02: Key Vault writer, consent flow and bootstrap admin (backend) |
| `docs/api/openapi.json` | 19-02: Key Vault writer, consent flow and bootstrap admin (backend) |
| `backend/app/onboarding.py` | 19-03: Wizard steps: create, connect and verify registrations (backend) |
| `backend/app/routers/onboarding.py` | 19-03: Wizard steps: create, connect and verify registrations (backend) |
| `backend/app/schemas.py` | 19-03: Wizard steps: create, connect and verify registrations (backend) |
| `backend/tests/test_onboarding.py` | 19-03: Wizard steps: create, connect and verify registrations (backend) |
| `docs/api/openapi.json` | 19-03: Wizard steps: create, connect and verify registrations (backend) |
| `frontend/src/nav/navConfig.ts` | 19-04: Setup wizard page (frontend) |

## Verification
- 19-01 (R19-1, R19-2): 8/8 verification commands passed
- 19-02 (R19-2, R19-3): 7/7 verification commands passed
- 19-03 (R19-2, R19-3): 7/7 verification commands passed
- 19-04 (R19-2, R19-3): 3/3 verification commands passed

## Agents
- 19-01: engineering-infrastructure-devops
- 19-02: engineering-security-engineer
- 19-03: engineering-backend-architect
- 19-04: engineering-frontend-developer

## Also Covered
- backend/tests/test_zz_api_contract.py
- backend/tests/test_zz_api_contract.py
- frontend/src/pages/admin/Setup.tsx
- frontend/src/pages/admin/Setup.test.tsx
- frontend/src/App.tsx
- frontend/src/api.ts
