# Client portal: Sign in with Microsoft (Entra SSO)

Portal contacts can sign in with their own work Microsoft account **as well as** with the emailed
one-time link. Both paths open the same portal session for the same contact record; the link keeps
working for every contact, so SSO is a convenience, never a lock-out.

This uses a **second, multi-tenant** app registration, separate from the single-tenant staff app in
[ENTRA_SETUP.md](ENTRA_SETUP.md). Never reuse the staff app: it must keep rejecting other tenants.

## 1. Register the portal application (in YOUR tenant)
Entra admin center -> **App registrations -> New registration**
- Name: `PSA client portal` (clients see this name on the consent screen)
- Supported account types: **Accounts in any organizational directory (multitenant)**. Not personal
  Microsoft accounts.
- Redirect URI (type *Web*): `https://<your PSA host>/api/v1/portal/sso/callback`

Then **Certificates & secrets -> New client secret** and copy the *Value* at once. Diary its expiry.

Only the delegated `openid`, `profile` and `email` scopes are requested. No Graph permissions.

## 2. Configure the PSA
| `.env` | Value |
|---|---|
| `PORTAL_ENTRA_CLIENT_ID` | The portal app's *Application (client) ID* |
| `PORTAL_ENTRA_CLIENT_SECRET` | The secret value from step 1 |
| `PUBLIC_URL` | The exact `https://` origin (must match the redirect URI host) |

Restart the app. `GET /api/v1/portal/login-options` then answers `{"sso": true}` (only while the portal
is also turned on in Settings), and the portal login page offers **Sign in with Microsoft**. With either
variable empty, SSO is off: the button disappears and `/api/v1/portal/sso/login` answers 404.

## 3. Per client: admin consent
A client's users can only sign in once **their** tenant trusts the app. Ask the client's Entra admin to
open this URL once and accept:

```
https://login.microsoftonline.com/<client tenant id>/adminconsent?client_id=<PORTAL_ENTRA_CLIENT_ID>
```

Their admin may also restrict who can use it (Enterprise applications -> PSA client portal ->
*Assignment required*) and apply their own Conditional Access (MFA).

## 4. Per client: set the tenant id on the organization
In the PSA, open the organization and set **Entra tenant id** to the client's *Directory (tenant) ID*
(a GUID; the client finds it in Entra admin center -> Overview). It is stored lower-case and must be
unique: two organizations can never claim the same tenant (409). **Only admins** (`portal:manage`) can
set or change it, because it decides whose Microsoft accounts reach that client's portal; anyone who can
edit organizations may clear it.

Contacts still need **portal access** as before. SSO never creates contacts.

## How a sign-in is matched
1. The ID token is validated by authlib (signature, expiry, nonce, PKCE). Because the PSA passes its own
   claims options (which replace authlib's defaults), it pins `aud` to `PORTAL_ENTRA_CLIENT_ID`
   explicitly, and because a multi-tenant app's issuer is a `{tenantid}` template, it requires `iss`
   to be exactly `https://login.microsoftonline.com/<tid>/v2.0` for the token's own `tid`.
2. `tid` and `oid` must be present. `tid` must match one organization's tenant id; that organization
   must not be archived.
3. Within **that organization only**, the contact is found by its bound Entra object id (`oid`), or, on
   a first sign-in, by email (`email`, else `preferred_username`, case-insensitive).
4. The contact must have portal access and not be archived. If it is already bound to a different
   `oid`, or the `oid` is bound to a contact of another organization, sign-in is refused.
5. **Matched by `oid`** (already linked): the contact is signed in directly.
6. **Matched by email only** (first sign-in): nothing is signed in and nothing is bound. The PSA emails
   the contact a one-time link ("confirm your Microsoft account"; the same link machinery, expiry and
   rate limits as the emailed sign-in link) that carries the pending binding, and redirects to
   `/portal?sso=confirm` ("Check your email..."). That redirect is the same whether the email was sent,
   rate-limited or mail is not configured. When a link was issued, the browser also gets a short-lived
   httponly cookie (`psa_portal_sso_confirm`, path `/api/v1/portal`, expires with the link) whose
   hash is stored on the link. Audited as `portal.sso_link_requested`
   (`{"contact_id", "sent", "reason"?}`) or, when rate-limited, `portal.sso_link_rate_limited`.
7. **Opening the confirm link** signs the contact in (it proves they control the mailbox). It binds the
   `oid` only when opened **in the same browser that did the Microsoft sign-in** (the cookie matches)
   and, after re-checking at that moment that the contact is still unlinked, no other contact holds the `oid`, and
   the organization's tenant id still equals the one the token came from, binds the `oid`
   (`portal.sso_linked`). If a re-check fails, the contact is still signed in but nothing is bound
   (`portal.sso_link_skipped` with `reason`: `different_browser`, `contact_already_linked`,
   `oid_bound_elsewhere` or `tenant_changed`). Opening the link in another browser or device
   therefore still signs you in but does not link the account; to link it, use Sign in with
   Microsoft again from the browser you will open the email in. The cookie is cleared once the link
   is used. If a concurrent binding of the same `oid` wins the race, the link is refused
   (`portal.login_failed`, `{"reason": "oid_conflict", "method": "sso_confirm"}`) and can be retried.
8. Later sign-ins match by `oid`, even if the email changes in Entra. The contact list shows **SSO
   linked**; **Unlink** clears it (and ends that contact's portal sessions) so the next sign-in has to
   be confirmed by email again, e.g. when a mailbox is handed to a new person.
9. **Changing or clearing an organization's tenant id** unlinks every contact of that organization
   that has an `oid` and ends their portal sessions (`organization.entra_tenant_changed` with
   `{"contacts_unlinked": n}`). Saving the same value again changes nothing.

Every refusal redirects to `/portal?sso=denied` with no detail, and is audited as
`portal.login_failed` with `{"reason": ..., "method": "sso"}`. Reasons: `not_configured`,
`portal_disabled`, `token_exchange`, `missing_tid`, `missing_oid`, `unknown_tenant`,
`organization_archived`, `oid_bound_elsewhere`, `missing_email`, `no_contact`, `contact_archived`,
`no_portal_access`, `oid_mismatch`. Successes are `portal.login` with `{"contact_id", "method": "sso"}`
(or `"sso_confirm"` when the confirm link was used).

## Trust note: the email claim
Entra does **not** verify the `email` / `preferred_username` claims: a tenant's admins can set any
address on any of their users, and an invited guest or ordinary member can end up carrying an address
equal to a portal contact's (for example the billing contact). The email claim is therefore only a
**candidate** match, and only inside the organization whose tenant issued the token, never another
client's. The first link between a Microsoft account and a contact is confirmed by a one-time link
sent to the contact's own mailbox, so whoever signs in with Microsoft must also control that mailbox.
The link only binds in the browser that did the Microsoft sign-in: otherwise a tenant member could sign
in carrying the contact's address and wait for the real contact to click the email, which would link
the member's account to the contact (account-linking CSRF). The real contact clicking it elsewhere is
just signed in as themselves.
That is why setting the tenant id is admin-only and unique, and why the `oid`, not the email, is the
lasting identity once bound.
