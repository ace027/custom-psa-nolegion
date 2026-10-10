# Microsoft Entra ID (SSO) setup

Staff sign in with Entra ID using OpenID Connect (authorization code + PKCE). The app is
**single-tenant**: tokens from any other tenant are rejected.

## 1. Register the application
Entra admin center → **App registrations → New registration**
- Name: `PSA`
- Supported account types: **Accounts in this organizational directory only** (single tenant)
- Redirect URI (type *Web*): `https://<your PSA host>/api/auth/callback`

## 2. Create a client secret
**Certificates & secrets → New client secret.** Copy the *Value* immediately. Put a calendar reminder
before it expires (choose 12 or 24 months).

## 3. Collect values for `.env`
| `.env` | Where to find it |
|---|---|
| `ENTRA_TENANT_ID` | App registration → Overview → *Directory (tenant) ID* |
| `ENTRA_CLIENT_ID` | Overview → *Application (client) ID* |
| `ENTRA_CLIENT_SECRET` | The secret value from step 2 |
| `PUBLIC_URL` | The exact `https://` origin users type (must match the redirect URI host) |

Only the delegated `openid`, `profile`, `email` scopes are used; no admin consent or Graph
permissions are needed for sign-in. (Mailbox permissions arrive with Phase 2.)

## 4. Optional hardening
- **Enterprise applications → PSA → Properties → Assignment required = Yes**, then assign only the
  staff who should see the PSA. Entra then blocks everyone else before the PSA is even involved.
- Apply your Conditional Access policies (MFA, compliant device) to this app.

## Who may sign in
The PSA never auto-creates users. An admin must first add the person on the **Users** page
(email + role). On first sign-in their Entra object id (`oid`) is bound to that record.
Deactivating a user ends their sessions immediately.

## First admin (one-time bootstrap)
There is no admin yet on a fresh production database, and the UI needs one. Insert it once:
```sh
docker compose exec db psql -U psa_owner -d psa -c \
  "INSERT INTO users (email, display_name, role) VALUES ('you@yourdomain.com', 'Your Name', 'admin');"
```
Then sign in with Microsoft using that address. This is recorded in the database only; add any
further staff through the UI so they are audited.

## Troubleshooting
Check **Audit log → filter `auth.`** in the UI. `auth.login_failed` rows carry a reason:
`not_provisioned`, `wrong_tenant`, `inactive`, `oid_mismatch`, `token_exchange`.
