# Deploying on Azure

`deploy/azure/deploy.sh` deploys the PSA to Azure Container Apps with PostgreSQL Flexible Server,
an Azure Files share for attachments and **every secret in Azure Key Vault**. Nothing secret is
written to an `.env`, the parameter file or the screen. Self-hosting with `docker-compose.yml`
is unchanged (see [DEVELOPMENT.md](DEVELOPMENT.md) and [ENTRA_SETUP.md](ENTRA_SETUP.md)).

## What gets created
| Resource | Name | Notes |
|---|---|---|
| Resource group | `$RESOURCE_GROUP` | Everything below lives in it |
| Entra app registration | `<prefix> PSA staff sign-in` | Single tenant, redirect `https://$PUBLIC_HOST/api/v1/auth/callback`, delegated `openid profile email User.Read` only |
| Key Vault | `<prefix>-kv-<suffix>` | RBAC mode, purge protection, 90-day soft delete |
| Managed identity | `<prefix>-id` | Key Vault Secrets User + Secrets Officer on the vault, AcrPull on the registry |
| Container registry | `<prefix>acr<suffix>` | Basic, admin user disabled; images `psa-api`, `psa-web`, `psa-proxy` |
| Log Analytics | `<prefix>-logs` | All container logs, 30 days |
| Virtual network | `<prefix>-vnet` | `apps` subnet (Container Apps) and `postgres` subnet (delegated) |
| PostgreSQL Flexible Server | `<prefix>-pg-<suffix>` | v16, Burstable B1ms, private access only, private DNS zone, database `psa` |
| Storage account | `<prefix>st<suffix>` | TLS 1.2, no public blob access; file share `attachments` |
| Container Apps environment | `<prefix>-env` | Mounts the share at `/data/attachments` |
| Container app `proxy` | | External ingress (HTTPS 443), Caddy serving the web app and forwarding `/api/*` |
| Container app `api` | | Internal ingress on 8000 (uvicorn), share mounted read-write |
| Container app `worker` | | No ingress, `python -m app.worker`, exactly one replica |
| Container Apps job `migrate` | | Creates the `psa_app` role, `alembic upgrade head`, then `python -m app.bootstrap_admin` |

`<suffix>` is six hex characters derived from the subscription and resource group, so names stay
the same across runs. The template is `deploy/azure/main.bicep`; `main.parameters.example.json`
shows its parameters (deploy.sh writes the real file to a temp directory and removes it).

## Prerequisites
- Azure CLI (`az`, signed in with `az login`), `bash`, `openssl`, `python3`.
- **Owner** (or Contributor + User Access Administrator) on the subscription: the script creates
  role assignments.
- In Entra ID, the right to register applications for the staff sign-in app (Application
  Developer is enough; the script stops with a clear message before deploying anything if you
  lack it).
- For the Setup wizard later: **Cloud Application Administrator** or **Global Administrator** in
  Entra, and **Exchange Organization Management** to scope the mail and calendar app to one
  mailbox ([MAIL_SETUP.md](MAIL_SETUP.md), [CALENDAR_SETUP.md](CALENDAR_SETUP.md)).
- Resource providers registered once per subscription:
  ```sh
  for p in Microsoft.App Microsoft.DBforPostgreSQL Microsoft.KeyVault Microsoft.ContainerRegistry \
           Microsoft.OperationalInsights Microsoft.Storage Microsoft.Network; do az provider register -n $p; done
  ```
- A DNS name for the PSA (for example `psa.example.com`) that you can add records to.

## Deploy
```sh
RESOURCE_GROUP=psa-prod LOCATION=westeurope NAME_PREFIX=psa \
PUBLIC_HOST=psa.example.com BOOTSTRAP_ADMIN_EMAIL=you@example.com \
  ./deploy/azure/deploy.sh
```
| Variable | Meaning |
|---|---|
| `RESOURCE_GROUP` | Created if missing |
| `LOCATION` | Azure region, e.g. `westeurope` |
| `NAME_PREFIX` | 2-12 chars, lowercase letters, digits and `-` |
| `PUBLIC_HOST` | Host name staff and clients use, no `https://` |
| `BOOTSTRAP_ADMIN_EMAIL` | The first admin; must match the `email` claim of that Entra account |

What it does, in order: checks `az login`; creates or reuses the staff sign-in app; creates the
resource group and Key Vault and gives you Key Vault Secrets Officer on it; generates the missing
secrets straight into the vault; builds the images with `az acr build`; deploys the
infrastructure; runs the `migrate` job and waits; deploys the apps; tries to bind `PUBLIC_HOST`
with a free managed certificate. It prints only the URL, the vault name and the next step.

**First run, DNS:** the bind fails until DNS exists. The script then prints two records, a
`CNAME` from `PUBLIC_HOST` to the proxy's Azure host name and a `TXT asuid.<host>` verification
record. Create them and re-run `deploy.sh`; it binds the host and keeps the binding on later runs.

Re-running is safe: existing secrets are never regenerated, the existing staff app is reused
(its redirect URI and permissions are reset to the values above), and the Key Vault comes back
from soft delete if the resource group was torn down.

## Where each secret lives
Every secret below is a Key Vault secret that Container Apps reads through the managed identity
(`keyVaultUrl` secret references) and hands to the containers as an environment variable.

| Key Vault secret | Env var | Created by | Used by |
|---|---|---|---|
| `session-secret` | `SESSION_SECRET` | deploy.sh (`openssl rand -base64 48`) | api, worker |
| `credentials-key` | `CREDENTIALS_KEY` | deploy.sh (Fernet key) | api, worker |
| `pg-admin-password` | (Bicep parameter) | deploy.sh | PostgreSQL admin `psa_owner` |
| `app-db-password` | `APP_DB_PASSWORD` | deploy.sh | migrate job (sets the `psa_app` password) |
| `migration-database-url` | `MIGRATION_DATABASE_URL` | deploy.sh | migrate job only |
| `database-url` | `DATABASE_URL` | deploy.sh | api, worker, migrate |
| `entra-client-secret` | `ENTRA_CLIENT_SECRET` | deploy.sh (staff app, 1-year secret) | api, worker |
| `portal-entra-client-id` | `PORTAL_ENTRA_CLIENT_ID` | Setup wizard (`unset` until then) | api, worker |
| `portal-entra-client-secret` | `PORTAL_ENTRA_CLIENT_SECRET` | Setup wizard | api, worker |
| `graph-tenant-id` | `GRAPH_TENANT_ID` | Setup wizard | api, worker |
| `graph-client-id` | `GRAPH_CLIENT_ID` | Setup wizard | api, worker |
| `graph-client-secret` | `GRAPH_CLIENT_SECRET` | Setup wizard | api, worker |
| `mail-mailbox` | `MAIL_MAILBOX` | Setup wizard | api, worker |

The value `unset` means "not configured" to the app. Plain (non-secret) settings set by the
template: `PUBLIC_URL`, `ENTRA_TENANT_ID`, `ENTRA_CLIENT_ID`, `ATTACHMENTS_DIR=/data/attachments`,
`ONBOARDING_ENABLED=true`, `KEY_VAULT_URL`, `AZURE_CLIENT_ID` (the managed identity),
`ENVIRONMENT=production`.

## First sign-in and the Setup wizard
1. Open `https://$PUBLIC_HOST` and sign in with Microsoft as `BOOTSTRAP_ADMIN_EMAIL` (the migrate
   job created that admin; no SQL needed).
2. Open **Setup**. The wizard creates or connects the portal SSO app and the Mail & Calendar app,
   writes their secrets straight into Key Vault and verifies each registration.
3. Restart the api and worker so they read the new values:

```sh
for app in api worker; do
  az containerapp revision restart -g "$RESOURCE_GROUP" -n "$app" --revision \
    "$(az containerapp revision list -g "$RESOURCE_GROUP" -n "$app" --query "[?properties.active].name | [0]" -o tsv)"
done
```

## Updating
Pull the new code and re-run `deploy.sh` with the same variables. It builds new images, runs
migrations with the new image **before** rolling out the new api, worker and proxy revisions, and
keeps every secret. Rollback: re-activate the previous revision
(`az containerapp revision list -n api -g ...`, then `az containerapp ingress traffic set` or
`revision activate`); note that migrations are not rolled back automatically.

## Backups
- **Database:** Flexible Server keeps automatic backups with point-in-time restore for
  `postgresBackupRetentionDays` (default 14, up to 35; change it in `main.bicep` and re-run).
  Restore to a new server: `az postgres flexible-server restore -g <rg> -n <new-name>
  --source-server <prefix>-pg-<suffix> --restore-time 2026-01-31T13:00:00Z`, then point
  `database-url` and `migration-database-url` at the new host and restart.
- **Attachments:** take share snapshots (schedule them with Azure Backup for file shares for
  retention):
  `az storage share-rm snapshot --storage-account <prefix>st<suffix> --name attachments`.
  Deleted shares are recoverable for 14 days (share soft delete).
- **Key Vault:** soft delete (90 days) and purge protection; deleted secrets can be recovered with
  `az keyvault secret recover`.

## Rotating secrets
Write new values from a file so they never touch the command line, then restart:
```sh
umask 077; f=$(mktemp)
openssl rand -base64 48 | tr -d '\n' >"$f"     # e.g. a new session secret
az keyvault secret set --vault-name <vault> --name session-secret --file "$f" -o none; rm -f "$f"
# then the restart loop from "First sign-in and the Setup wizard"
```
- **Staff SSO secret** (yearly, it expires):
  `az ad app credential reset --id <staff app id> --years 1 --query password -o tsv | tr -d '\n' >"$f"`,
  then `secret set` as above and restart.
- **credentials-key:** set the secret to `<new>,<old>` (new first), restart, run the existing
  rekey job `az containerapp exec -g <rg> -n api --command "python -m app.rekey"`, then set it to
  `<new>` only and restart again (see [INTEGRATIONS.md](INTEGRATIONS.md)).
- **app-db-password:** set a new value (letters and digits only), update `database-url` to match,
  start the migrate job (`az containerapp job start -n migrate -g <rg>`; it re-applies the role
  password), then restart.
- **pg-admin-password:** set a new value, update `migration-database-url` to match and re-run
  `deploy.sh` (the template applies the password).

## Cost (rough, pay-as-you-go, per month)
| Item | Estimate |
|---|---|
| Container Apps (api, worker, proxy at one replica each) | about $40-70 |
| PostgreSQL B1ms + 32 GB storage + backups | about $20 |
| Container Registry Basic | about $5 |
| Log Analytics | about $2-3 per GB ingested |
| Key Vault, Azure Files, VNet, private DNS | a few dollars |

Check the Azure pricing calculator for your region; scale `maxReplicas` and the PostgreSQL SKU in
`main.bicep` as usage grows.

## Tear-down
```sh
az group delete -n "$RESOURCE_GROUP"
az ad app delete --id <staff app id>   # and the apps the wizard created, if you want them gone
```
The Key Vault stays soft-deleted for 90 days and cannot be purged early (purge protection);
re-running `deploy.sh` with the same resource group recovers it with its secrets.

## Troubleshooting
- Logs: Log Analytics workspace `<prefix>-logs`, or
  `az containerapp logs show -n api -g "$RESOURCE_GROUP" --follow`.
- Migrate job failed: `az containerapp job logs show -n migrate -g "$RESOURCE_GROUP" --execution <name> --container migrate`.
- A first deploy failing on image pull or secret access usually means a new role assignment had
  not applied yet; the script retries once, and a re-run fixes it.
