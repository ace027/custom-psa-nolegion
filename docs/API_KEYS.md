# API keys

API keys let scripts and tools such as n8n call the API without a browser session.

## Creating a key

An admin opens **API keys** in the navigation (or calls `POST /api/v1/api-keys`), gives the key a name,
ticks the permissions it needs and chooses an expiry (1 to 730 days, default 365).

The token is shown **once**, in the create response and on screen. Only its SHA-256 hash is stored,
so it cannot be recovered. Copy it immediately; if it is lost, revoke the key and create another.

## Using a key

```
Authorization: Bearer psa_<prefix>_<secret>
```

No cookie and no `X-Requested-With` header are needed. Bearer requests are exempt from the CSRF
header check, because browsers never attach this header by themselves. Any other `Authorization`
value is ignored and the normal cookie session applies.

## Scopes

A key carries a list of permissions (for example `ticket:read`, `ticket:write`). A request is
allowed only if the key lists the permission **and** the owner's role still holds it. Demoting the
owner therefore narrows the key at once (403 on routes it no longer reaches). A key can only be
given permissions the creating admin holds.

Keys can never hold `user:manage`, `apikey:manage` or `portal:manage`. Endpoints that need only a
login (such as `/api/v1/auth/me`) and the API key routes themselves refuse keys with 403.

## Expiry, revocation and owner status

A key stops working (401) when it expires, is revoked, or its owner is deactivated.
Revoke from the page or `POST /api/v1/api-keys/{id}/revoke`. Revoking twice returns 409.

## Audit

Key creation and revocation are audited without the token or hash. Changes made through a key are
audited as the owner with `api_key_id` in the entry detail. Failed attempts are recorded as
`auth.api_key_rejected` (with the 8-character prefix only), and scope failures as `auth.denied`.
`last_used_at` is updated at most once every 5 minutes.

See [API.md](API.md) for the `/api/v1` base path, versioning policy and the committed OpenAPI spec.
