# Plan 19-01 Summary: Azure deployment: Bicep, deploy script and guide

## Result
**Status**: Complete with Warnings
**Wave**: 1
**Agent**: engineering-infrastructure-devops
**Completed**: 2026-11-03

## Agent Selection Rationale

| Candidate | Semantic | Heuristic | Memory | Total | Source |
|-----------|----------|-----------|--------|-------|--------|
| engineering-infrastructure-devops | — | 23 | 0 | 23 | mandatory |
| engineering-senior-developer | — | 20 | 3.07 | 23.07 | heuristic |
| engineering-backend-architect | — | 18 | 2.99 | 20.990000000000002 | heuristic |

- **Task type detected**: implementation
- **Confidence**: LOW
- **Adapter**: claude-code
- **Model tier**: sonnet

## Completed Tasks
- [x] Task 1: main.bicep (done)
- [x] Task 2: deploy.sh (done)
- [x] Task 3: AZURE_DEPLOY.md (done)

## Files Modified
- `deploy/azure/deploy.sh`
- `deploy/azure/main.bicep`
- `deploy/azure/main.parameters.example.json`
- `docs/AZURE_DEPLOY.md`
- `docs/ENTRA_SETUP.md`

## Verification Results
8/8 verification commands passed (run by Triad after the agent finished).

## Verification Commands
| Command | Exit Code | Result |
|---------|-----------|--------|
| `bash -n deploy/azure/deploy.sh` | 0 | PASS |
| `grep -q 'keyVaultUrl' deploy/azure/main.bicep` | 0 | PASS |
| `test -f docs/AZURE_DEPLOY.md` | 0 | PASS |
| `test -f deploy/azure/main.bicep && grep -q 'keyVaultUrl' deploy/azure/main.bicep && grep -q 'enableRbacAuthorization: true' deploy/azure/main.bicep && grep -q 'Microsoft.DBforPostgreSQL/flexibleServers' deploy/azure/main.bicep && grep -q 'Microsoft.App/jobs' deploy/azure/main.bicep` | 0 | PASS |
| `! grep -Eiq '(password\|secret)\s*[:=]\s*.[A-Za-z0-9+/]{12,}' deploy/azure/main.parameters.example.json` | 0 | PASS |
| `grep -q 'set -euo pipefail' deploy/azure/deploy.sh && ! grep -q 'set -x' deploy/azure/deploy.sh` | 0 | PASS |
| `grep -q 'AzureADMyOrg' deploy/azure/deploy.sh && grep -q 'trap' deploy/azure/deploy.sh` | 0 | PASS |
| `grep -q 'deploy.sh' docs/AZURE_DEPLOY.md && grep -q 'Key Vault' docs/AZURE_DEPLOY.md && grep -q 'revision restart' docs/AZURE_DEPLOY.md && grep -q 'AZURE_DEPLOY.md' docs/ENTRA_SETUP.md` | 0 | PASS |

## Key Decisions
- deploy.sh creates the Key Vault and ACR before Bicep (the secrets must exist before Bicep references them, and the images must be built before apps deploy). Bicep declares both again with the same settings, so they are enforced on every run.
- Names come from a 6-hex suffix (sha256 of subscription/resource group), passed to Bicep as `suffix`. That way deploy.sh knows the PG host and can build database-url / migration-database-url (`?sslmode=require`) before deploying.
- Two-pass deploy: Bicep `deployApps=false`, then the migrate job, then `deployApps=true`. Migrations run before new app code, and the first deploy does not fail on an api whose database role does not exist yet.
- Flexible Server has no init scripts, so the migrate job creates or ALTERs the `psa_app` role (psycopg, password as sql.Literal) from a new secret `app-db-password`. Then it runs `alembic upgrade head`, then `python -m app.bootstrap_admin` if `BOOTSTRAP_ADMIN_EMAIL` is set.
- The proxy image is the web image plus deploy/Caddyfile, adapted at build time in a temp directory: upstream becomes `http://api` with `header_up Host {upstream_hostport}`, plus `trusted_proxies private_ranges`. Container Apps internal ingress does not expose `api:8000`. If `reverse_proxy api:8000` ever leaves the Caddyfile, the script stops with an error.
- The custom domain is bound with a managed certificate after the deploy. Later runs look up the certificate id and pass it to Bicep so a redeploy does not drop the binding. Until DNS exists the script prints the CNAME and TXT records to create.
- The api mounts the share read-write (compose mounts it read-only), as the plan says. The owner DB URL and app-db-password go only to the migrate job; api and worker share one set of runtime secrets.

## Issues Encountered
- A `'` inside `${VAR:?...}` broke bash parsing; reworded the message and fixed it.

## Escalations
| # | Severity | Type | Decision | Status | Resolution |
|---|----------|------|----------|--------|------------|
| 1 | info | accepted-risk | The managed identity has Key Vault Secrets Officer on the vault (from the plan and CONTEXT), so the running api could overwrite any secret in it, including database URLs. Key Vault and storage keep public network access. | pending | INVALID: type "accepted-risk" is not one of architecture, dependency, scope, schema, api, deletion, infrastructure, quality |

- #1 context: For the security review (R19-4). Hardening options are a separate vault for wizard-managed secrets, or private endpoints for Key Vault and storage.

## Handoff Context
- **Key outputs**: deploy/azure/deploy.sh; deploy/azure/main.bicep; deploy/azure/main.parameters.example.json; docs/AZURE_DEPLOY.md; docs/ENTRA_SETUP.md
- **Decisions made**: deploy.sh creates the Key Vault and ACR before Bicep (the secrets must exist before Bicep references them, and the images must be built before apps deploy). Bicep declares both again with the same settings, so they are enforced on every run.; Names come from a 6-hex suffix (sha256 of subscription/resource group), passed to Bicep as `suffix`. That way deploy.sh knows the PG host and can build database-url / migration-database-url (`?sslmode=require`) before deploying.; Two-pass deploy: Bicep `deployApps=false`, then the migrate job, then `deployApps=true`. Migrations run before new app code, and the first deploy does not fail on an api whose database role does not exist yet.; Flexible Server has no init scripts, so the migrate job creates or ALTERs the `psa_app` role (psycopg, password as sql.Literal) from a new secret `app-db-password`. Then it runs `alembic upgrade head`, then `python -m app.bootstrap_admin` if `BOOTSTRAP_ADMIN_EMAIL` is set.; The proxy image is the web image plus deploy/Caddyfile, adapted at build time in a temp directory: upstream becomes `http://api` with `header_up Host {upstream_hostport}`, plus `trusted_proxies private_ranges`. Container Apps internal ingress does not expose `api:8000`. If `reverse_proxy api:8000` ever leaves the Caddyfile, the script stops with an error.; The custom domain is bound with a managed certificate after the deploy. Later runs look up the certificate id and pass it to Bicep so a redeploy does not drop the binding. Until DNS exists the script prints the CNAME and TXT records to create.; The api mounts the share read-write (compose mounts it read-only), as the plan says. The owner DB URL and app-db-password go only to the migrate job; api and worker share one set of runtime secrets.
- **Open questions**: (none)
- **Conventions established**: The Bicep sets env vars KEY_VAULT_URL, AZURE_CLIENT_ID and ONBOARDING_ENABLED=true; the wizard-managed secrets start as `unset`. This matches what 19-02's config.py now expects.; Key Vault secret names the wizard (19-03) writes: portal-entra-client-id, portal-entra-client-secret, graph-tenant-id, graph-client-id, graph-client-secret, mail-mailbox.; Restart the wizard should show (19-04): `az containerapp revision restart` on both `api` and `worker`, using the active revision (exact loop in AZURE_DEPLOY.md). Container app names are fixed as api, worker, proxy and the job is migrate.; The migrate job gets MIGRATION_DATABASE_URL, which is what 19-02's bootstrap_admin.py uses.

## Requirements Covered
- R19-1
- R19-2

## Token Usage
25 requests, 1499052 input tokens (1408261 cached), 54862 output tokens, $1.8328
