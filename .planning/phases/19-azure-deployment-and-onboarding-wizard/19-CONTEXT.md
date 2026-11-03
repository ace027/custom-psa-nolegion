# Phase 19: Azure deployment and onboarding wizard -- Context

## Phase Goal
The PSA runs on Azure in Docker with its secrets in Azure Key Vault, and a first-run wizard creates and connects the SSO, Mail and Calendar app registrations.

## Requirements Covered
- R19-1 (owner note 3): a documented, repeatable Azure deployment (container hosting, PostgreSQL, storage for attachments) with secrets read from Key Vault, none in .env
- R19-2: an admin-only first-run onboarding wizard that creates or connects the staff SSO, portal SSO, Mail and Calendar app registrations with least-privilege permissions, and verifies each
- R19-3: secrets created by the wizard go straight to Key Vault and are never shown again or logged
- R19-4: security review passes with no unresolved CRITICAL/HIGH findings

## What Already Exists (from prior phases)
- backend/app/config.py: pydantic-settings Settings from env/.env, lru_cached get_settings; secrets session_secret, database_url, migration_database_url, entra_client_secret, portal_entra_client_secret, graph_client_secret, credentials_key (Fernet, rotation via rekey.py); no Azure SDK, no MSAL; authlib for OIDC
- Staff SSO: routers/auth.py + auth/oidc.py (entra_tenant_id/client_id/secret, redirect from public_url); portal SSO: routers/portal.py + auth/oidc.py (portal_entra_*; multi-tenant app, redirect /api/v1/portal/sso/callback); mail and calendar share ONE Graph app (graph_tenant_id/client_id/secret) scoped by Exchange RBAC for Applications (docs/MAIL_SETUP.md, docs/CALENDAR_SETUP.md say grant no Entra mail permissions)
- backend/app/crypto.py encrypt_credentials/decrypt (MultiFernet) already encrypts integration and webhook secrets in the DB
- Attachments live on disk under attachments_dir (/data/attachments); outbound mail attachments are bytea
- docker-compose.yml: db, migrate, api, worker, proxy (Caddy built from frontend); deploy/ has Caddyfile, backup.sh, restore.sh, postgres-init/01-roles.sh (psa_owner / app roles for RLS)
- First admin today is a manual SQL INSERT (docs/ENTRA_SETUP.md); no /setup route exists
- Alembic head after Phase 18 is 0042
- No az or bicep CLI in the build sandbox: infra files are checked statically

## Key Design Decisions
- ASSUMED hosting: Azure Container Apps (one environment; container apps api, worker and proxy with external ingress on proxy only, migrate as a Container Apps Job), Azure Database for PostgreSQL Flexible Server (private access in a VNet), an Azure Files share mounted at /data/attachments, Log Analytics, Azure Container Registry, Key Vault (RBAC mode, purge protection) and one user-assigned managed identity; IaC in Bicep (deploy/azure/main.bicep) driven by deploy/azure/deploy.sh (az CLI), documented in docs/AZURE_DEPLOY.md; docker-compose stays for self-hosting
- Secrets reach the app as environment variables through Container Apps Key Vault secret references (keyVaultUrl + identity), so the app code keeps reading env and no Azure SDK is added; nothing secret is written to any .env on Azure
- The deploy script generates session_secret, credentials_key and the PostgreSQL passwords straight into Key Vault (az keyvault secret set from generated values, never echoed), and pre-creates every wizard-managed Key Vault secret with the placeholder value 'unset'; config.py treats the literal 'unset' as empty
- ASSUMED bootstrap: the staff SSO app registration is created by deploy.sh (az ad app create, single-tenant, web redirect https://<host>/api/v1/auth/callback, delegated openid profile email User.Read only) because nothing can sign in before it exists; deploy.sh also inserts the first admin by email (BOOTSTRAP_ADMIN_EMAIL) through the migrate job, replacing the manual SQL step
- ASSUMED wizard power: the admin grants a one-time delegated consent (incremental consent on the staff SSO app) for Application.ReadWrite.All, AppRoleAssignment.ReadWrite.All and DelegatedPermissionGrant.ReadWrite.All; the access token is stored only encrypted (crypto.encrypt_credentials) in a new onboarding_tokens row with expires_at, never in the session cookie, never logged, and deleted on finish or expiry; 'Finish' also deletes the oauth2PermissionGrant for those scopes so the SSO app keeps no admin power
- Mail and Calendar stay ONE app registration ('PSA Mail & Calendar') with NO Entra API permissions, as today; least privilege comes from Exchange RBAC for Applications, which Graph cannot configure, so the wizard shows the exact PowerShell from MAIL_SETUP/CALENDAR_SETUP with the ids filled in and then verifies the scope (support mailbox readable, an out-of-scope staff mailbox returns 403)
- The portal SSO app is created multi-tenant with delegated openid profile email only and the portal redirect URI
- Secrets created by the wizard (addPassword on the new apps) are written to Key Vault by the managed identity through the Key Vault REST API (httpx, IDENTITY_ENDPOINT/IDENTITY_HEADER token, api-version 7.4) and never returned, shown or logged; secret values are held only in local variables for the PUT
- The managed identity has 'Key Vault Secrets User' on the vault plus 'Key Vault Secrets Officer' scoped to the vault for the wizard; recorded as an accepted risk in the security review
- New values take effect after a restart: the wizard says so and shows the one az containerapp revision restart command; the app does not get rights to restart itself
- Wizard access: admin role only (require(P.CONFIG_MANAGE) plus ctx.user.role == 'admin'), every step audited (onboarding.*), POSTs CSRF-protected like the rest of the API, consent callback validates a one-time state bound to the admin's session
- Wizard availability: only when settings ONBOARDING_ENABLED is true (default true on Azure via Bicep, false in compose); after Finish it stays reachable read-only as a status page

## Plan Structure
- **Plan 19-01 (Wave 1)**: Azure deployment: Bicep, deploy script and guide -- A repeatable Azure deployment on Container Apps with PostgreSQL Flexible Server, Azure Files for attachments and every secret in Key Vault, plus the staff SSO bootstrap and first admin.
- **Plan 19-02 (Wave 1)**: Key Vault writer, consent flow and bootstrap admin (backend) -- Server-side pieces the wizard needs: a Key Vault secret writer using the managed identity, an encrypted short-lived store for the admin's consent token, the admin-only consent start/callback routes, and the bootstrap-admin command.
- **Plan 19-03 (Wave 2)**: Wizard steps: create, connect and verify registrations (backend) -- Create or connect the portal SSO and Mail & Calendar app registrations with least privilege, put their secrets straight into Key Vault, verify every registration including the staff SSO, and revoke the admin consent on finish.
- **Plan 19-04 (Wave 3)**: Setup wizard page (frontend) -- An admin-only /setup page that walks through Microsoft consent, creating or connecting each registration, the Exchange scope commands, restart and verification, then Finish.
