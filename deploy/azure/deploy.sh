#!/usr/bin/env bash
# Deploy or update the PSA on Azure (docs/AZURE_DEPLOY.md). Safe to re-run: existing Key Vault
# secrets and the existing staff sign-in app are kept; only missing ones are created.
#
#   RESOURCE_GROUP=psa-prod LOCATION=westeurope NAME_PREFIX=psa \
#   PUBLIC_HOST=psa.example.com BOOTSTRAP_ADMIN_EMAIL=you@example.com ./deploy/azure/deploy.sh
#
# Secret values never appear on the command line, on screen or in a file left behind: they are
# generated into a private temp directory (umask 077), passed to az with --file and removed on exit.
set -euo pipefail

: "${RESOURCE_GROUP:?set RESOURCE_GROUP}"
: "${LOCATION:?set LOCATION, e.g. westeurope}"
: "${NAME_PREFIX:?set NAME_PREFIX, e.g. psa}"
: "${PUBLIC_HOST:?set PUBLIC_HOST, e.g. psa.example.com}"
: "${BOOTSTRAP_ADMIN_EMAIL:?set BOOTSTRAP_ADMIN_EMAIL to the sign-in address of the first admin}"

die() { printf 'deploy.sh: %s\n' "$*" >&2; exit 1; }
step() { printf '==> %s\n' "$*" >&2; }

[[ "$NAME_PREFIX" =~ ^[a-z][a-z0-9-]{1,11}$ ]] || die "NAME_PREFIX must be 2-12 chars: lowercase letters, digits, '-'"
[[ "$PUBLIC_HOST" =~ ^[A-Za-z0-9.-]+$ ]] || die "PUBLIC_HOST must be a bare host name (no https://, no path)"
for tool in az openssl python3; do
  command -v "$tool" >/dev/null || die "$tool is required"
done

here=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$here/../.." && pwd)

umask 077
work=$(mktemp -d)
cleanup() {
  if command -v shred >/dev/null; then find "$work" -type f -exec shred -u {} + 2>/dev/null || true; fi
  rm -rf "$work"
}
trap cleanup EXIT
trap 'exit 130' INT TERM

# ---------------------------------------------------------------- sign-in
az account show -o none 2>/dev/null || die "not signed in: run 'az login' and 'az account set -s <subscription>'"
subscription=$(az account show --query id -o tsv)
tenant=$(az account show --query tenantId -o tsv)
if [ "$(az account show --query user.type -o tsv)" = "user" ]; then
  operator=$(az ad signed-in-user show --query id -o tsv); operator_type=User
else
  operator=$(az ad sp show --id "$(az account show --query user.name -o tsv)" --query id -o tsv); operator_type=ServicePrincipal
fi

rg_lower=$(printf '%s' "$RESOURCE_GROUP" | tr '[:upper:]' '[:lower:]')
suffix=$(python3 -c 'import hashlib,sys; print(hashlib.sha256(sys.argv[1].encode()).hexdigest()[:6])' "$subscription/$rg_lower")
vault="${NAME_PREFIX}-kv-${suffix}"
acr="$(printf '%s' "$NAME_PREFIX" | tr -d '-')acr${suffix}"
env_name="${NAME_PREFIX}-env"
pg_host="${NAME_PREFIX}-pg-${suffix}.postgres.database.azure.com"
tag="$(date -u +%Y%m%d%H%M%S)$(git -C "$repo" rev-parse --short HEAD 2>/dev/null | sed 's/^/-/' || true)"

# ---------------------------------------------------------------- staff sign-in app (Entra)
# Done first: if the operator lacks Entra rights we stop before anything is deployed.
entra_denied() {
  printf 'deploy.sh: Entra ID refused: %s\n' "$(head -n1 "$work/err" 2>/dev/null)" >&2
  die "your account cannot create or update the staff sign-in app registration. Ask for the Application Developer or Cloud Application Administrator role (or Global Administrator), then re-run. Nothing was deployed."
}
app_name="${NAME_PREFIX} PSA staff sign-in"
redirect="https://${PUBLIC_HOST}/api/v1/auth/callback"
# The wizard's admin-consent flow returns here (backend/app/onboarding_auth.py); both must be registered.
consent_redirect="https://${PUBLIC_HOST}/api/v1/onboarding/consent/callback"
# Microsoft Graph delegated openid, profile, email, User.Read; nothing else.
cat > "$work/graph-access.json" <<'JSON'
[{"resourceAppId": "00000003-0000-0000-c000-000000000000", "resourceAccess": [
  {"id": "37f7f235-527c-4136-accd-4a02d197296e", "type": "Scope"},
  {"id": "14dad69e-099b-42c9-810b-d002981feec1", "type": "Scope"},
  {"id": "64a6cdd6-aab1-4aaf-94b8-3cc8405e90d0", "type": "Scope"},
  {"id": "e1fe6dd8-ba31-4d61-89e7-88639da4683d", "type": "Scope"}]}]
JSON
step "staff sign-in app '$app_name'"
app_id=$(az ad app list --filter "displayName eq '$app_name'" --query '[0].appId' -o tsv 2>"$work/err") || entra_denied
if [ -z "$app_id" ]; then
  app_id=$(az ad app create --display-name "$app_name" --sign-in-audience AzureADMyOrg \
    --web-redirect-uris "$redirect" "$consent_redirect" --required-resource-accesses @"$work/graph-access.json" \
    --query appId -o tsv 2>"$work/err") || entra_denied
else
  az ad app update --id "$app_id" --sign-in-audience AzureADMyOrg --web-redirect-uris "$redirect" "$consent_redirect" \
    --required-resource-accesses @"$work/graph-access.json" -o none 2>"$work/err" || entra_denied
fi
az ad sp show --id "$app_id" -o none 2>/dev/null \
  || az ad sp create --id "$app_id" -o none 2>"$work/err" || entra_denied

# ---------------------------------------------------------------- resource group and vault
step "resource group $RESOURCE_GROUP"
az group create -n "$RESOURCE_GROUP" -l "$LOCATION" -o none

step "key vault $vault"
if ! az keyvault show -n "$vault" -g "$RESOURCE_GROUP" -o none 2>/dev/null; then
  if [ -n "$(az keyvault list-deleted --query "[?name=='$vault'].name" -o tsv)" ]; then
    az keyvault recover -n "$vault" -o none # purge protection: a torn-down vault comes back
  else
    az keyvault create -n "$vault" -g "$RESOURCE_GROUP" -l "$LOCATION" \
      --enable-rbac-authorization true --enable-purge-protection true --retention-days 90 \
      --enabled-for-template-deployment true -o none
  fi
fi
vault_id=$(az keyvault show -n "$vault" -g "$RESOURCE_GROUP" --query id -o tsv)
if [ "$(az role assignment list --assignee "$operator" --role 'Key Vault Secrets Officer' --scope "$vault_id" --query 'length(@)' -o tsv)" = "0" ]; then
  az role assignment create --assignee-object-id "$operator" --assignee-principal-type "$operator_type" \
    --role 'Key Vault Secrets Officer' --scope "$vault_id" -o none
fi
# Wait for the role to apply. Listing must succeed before "absent" can be trusted, or a re-run
# could overwrite a live password.
for _ in $(seq 1 30); do
  if az keyvault secret list --vault-name "$vault" --query '[].name' -o tsv >"$work/names" 2>/dev/null; then
    ok=1; break
  fi
  sleep 10
done
[ "${ok:-}" = 1 ] || die "cannot list secrets in $vault (role assignment not applied yet?); re-run in a few minutes"

has_secret() { grep -qx "$1" "$work/names"; }
put_secret() { # name file
  az keyvault secret set --vault-name "$vault" --name "$1" --file "$2" --encoding utf-8 -o none
  rm -f "$2"
  step "created Key Vault secret $1"
}
ensure_secret() { # name generator...
  local name=$1; shift
  has_secret "$name" && return 0
  "$@" >"$work/$name"
  put_secret "$name" "$work/$name"
}
gen_session_secret() { openssl rand -base64 48 | tr -d '\n'; }
gen_fernet_key() { python3 -c 'import base64,os,sys; sys.stdout.write(base64.urlsafe_b64encode(os.urandom(32)).decode())'; }
# URL-safe, and meets the Flexible Server rule (3 of: upper, lower, digit, symbol).
gen_db_password() {
  python3 -c '
import secrets, string, sys
a = string.ascii_letters + string.digits
while True:
    p = "".join(secrets.choice(a) for _ in range(40))
    if any(c.islower() for c in p) and any(c.isupper() for c in p) and any(c.isdigit() for c in p):
        break
sys.stdout.write(p)'
}
gen_unset() { printf 'unset'; }
ensure_db_url() { # name role password-secret
  has_secret "$1" && return 0
  local pw
  pw=$(az keyvault secret show --vault-name "$vault" --name "$3" --query value -o tsv)
  printf 'postgresql+psycopg://%s:%s@%s:5432/psa?sslmode=require' "$2" "$pw" "$pg_host" >"$work/$1"
  pw=''
  put_secret "$1" "$work/$1"
}

ensure_secret session-secret gen_session_secret
ensure_secret credentials-key gen_fernet_key
ensure_secret pg-admin-password gen_db_password
ensure_secret app-db-password gen_db_password
ensure_db_url migration-database-url psa_owner pg-admin-password
ensure_db_url database-url psa_app app-db-password
# Filled in later by the Setup wizard; Container Apps cannot reference a missing secret.
for name in portal-entra-client-id portal-entra-client-secret graph-tenant-id graph-client-id graph-client-secret mail-mailbox; do
  ensure_secret "$name" gen_unset
done
if ! has_secret entra-client-secret; then
  if ! az ad app credential reset --id "$app_id" --years 1 --display-name psa-deploy --query password -o tsv \
      2>"$work/err" | tr -d '\r\n' >"$work/entra-client-secret"; then
    entra_denied
  fi
  [ -s "$work/entra-client-secret" ] || entra_denied
  put_secret entra-client-secret "$work/entra-client-secret"
fi

# ---------------------------------------------------------------- images
step "container registry $acr"
az acr show -n "$acr" -g "$RESOURCE_GROUP" -o none 2>/dev/null \
  || az acr create -n "$acr" -g "$RESOURCE_GROUP" -l "$LOCATION" --sku Basic --admin-enabled false -o none
login_server=$(az acr show -n "$acr" -g "$RESOURCE_GROUP" --query loginServer -o tsv)

step "building images (tag $tag)"
az acr build -r "$acr" -t "psa-api:$tag" "$repo/backend" -o none
az acr build -r "$acr" -t "psa-web:$tag" "$repo/frontend" -o none
# Proxy = web image + deploy/Caddyfile adapted to Container Apps: the api is reached through the
# environment's internal ingress (http://api, routed by Host), and the forwarded client IP and
# scheme from the Azure ingress are trusted.
mkdir "$work/proxy"
python3 - "$repo/deploy/Caddyfile" "$work/proxy/Caddyfile" <<'PY'
import sys
src = open(sys.argv[1]).read()
old = "reverse_proxy api:8000"
if old not in src:
    sys.exit("deploy/Caddyfile no longer contains '%s'; update deploy.sh" % old)
new = "reverse_proxy http://api {\n\t\t\theader_up Host {upstream_hostport}\n\t\t}"
head = "{\n\tservers {\n\t\ttrusted_proxies static private_ranges\n\t}\n}\n\n"
open(sys.argv[2], "w").write(head + src.replace(old, new))
PY
printf 'FROM %s/psa-web:%s\nCOPY Caddyfile /etc/caddy/Caddyfile\n' "$login_server" "$tag" >"$work/proxy/Dockerfile"
az acr build -r "$acr" -t "psa-proxy:$tag" "$work/proxy" -o none

# ---------------------------------------------------------------- infrastructure and apps
cert_id=$(az containerapp env certificate list -g "$RESOURCE_GROUP" -n "$env_name" --managed-certificates-only \
  --query "[?properties.subjectName=='$PUBLIC_HOST'].id | [0]" -o tsv 2>/dev/null || true)

write_params() { # deployApps (values reach python through the environment, never its source)
  DEPLOY_APPS=$1 SUFFIX=$suffix TAG=$tag TENANT=$tenant APP_ID=$app_id CERT_ID=$cert_id VAULT_ID=$vault_id \
  python3 - "$work/params.json" <<'PY'
import json, os, sys
e = os.environ
p = {
    "namePrefix": e["NAME_PREFIX"], "suffix": e["SUFFIX"], "location": e["LOCATION"],
    "publicHost": e["PUBLIC_HOST"], "imageTag": e["TAG"], "entraTenantId": e["TENANT"],
    "entraClientId": e["APP_ID"], "bootstrapAdminEmail": e["BOOTSTRAP_ADMIN_EMAIL"],
    "customDomainCertificateId": e["CERT_ID"], "deployApps": e["DEPLOY_APPS"] == "true",
}
params = {k: {"value": v} for k, v in p.items()}
params["postgresAdminPassword"] = {
    "reference": {"keyVault": {"id": e["VAULT_ID"]}, "secretName": "pg-admin-password"}}
json.dump({"$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentParameters.json#",
           "contentVersion": "1.0.0.0", "parameters": params}, open(sys.argv[1], "w"))
PY
}
deploy() { # deployApps
  write_params "$1"
  az deployment group create -g "$RESOURCE_GROUP" -n "psa-$1-$tag" -f "$here/main.bicep" \
    -p @"$work/params.json" --query properties.outputs -o json >"$work/outputs.json"
}
deploy_with_retry() {
  if ! deploy "$1"; then
    step "deployment failed; retrying once in 60s (new role assignments can take a minute to apply)"
    sleep 60
    deploy "$1"
  fi
}

# Pass 1: everything but the apps, so migrations run before new app code serves traffic.
step "deploying infrastructure"
deploy_with_retry false

step "running migrations (and first-admin bootstrap)"
execution=$(az containerapp job start -n migrate -g "$RESOURCE_GROUP" --query name -o tsv)
status=""
for _ in $(seq 1 120); do
  status=$(az containerapp job execution show -n migrate -g "$RESOURCE_GROUP" --job-execution-name "$execution" \
    --query properties.status -o tsv)
  case "$status" in
    Succeeded) break ;;
    Failed|Stopped|Degraded)
      die "migrate job $status. Logs: az containerapp job logs show -n migrate -g $RESOURCE_GROUP --execution $execution --container migrate" ;;
  esac
  sleep 10
done
[ "$status" = Succeeded ] || die "migrate job still '$status' after 20 minutes; check it in the portal"

step "deploying apps"
deploy_with_retry true
fqdn=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["proxyFqdn"]["value"])' "$work/outputs.json")
verification_id=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["customDomainVerificationId"]["value"])' "$work/outputs.json")

# ---------------------------------------------------------------- custom domain
if [ -z "$cert_id" ]; then
  step "binding $PUBLIC_HOST with a managed certificate"
  if ! az containerapp hostname bind -g "$RESOURCE_GROUP" -n proxy --hostname "$PUBLIC_HOST" \
      --environment "$env_name" --validation-method CNAME -o none 2>"$work/err"; then
    printf '\nDNS is not ready for %s. Create these records, then re-run deploy.sh:\n' "$PUBLIC_HOST" >&2
    printf '  CNAME %s -> %s\n' "$PUBLIC_HOST" "$fqdn" >&2
    printf '  TXT   asuid.%s -> %s\n\n' "$PUBLIC_HOST" "$verification_id" >&2
  fi
fi

printf 'URL:       https://%s\n' "$PUBLIC_HOST"
printf 'Key Vault: %s\n' "$vault"
printf 'Next step: sign in as %s and open Setup\n' "$BOOTSTRAP_ADMIN_EMAIL"
