# API

Base path: `/api/v1`. Interactive docs are at `/api/v1/docs`; the raw spec is served at
`/api/v1/openapi.json`. The only unversioned routes are the health probes `/healthz` and `/readyz`.

## Versioning policy

- Additive changes (new endpoints, new optional fields, new enum values) stay in v1.
- A breaking change ships as `/api/v2`, and v1 is kept for a deprecation window.
- Pre-release there are no v1 consumers, so v1 may still be corrected before the first release.

## The committed spec

`docs/api/openapi.json` is the committed OpenAPI spec. Shared TypeScript clients are generated from it.
Regenerate it after any API change:

```
cd backend && python -m app.openapi_export
```

`python -m app.openapi_export --check` exits 1 when the file is stale, and the test
`backend/tests/test_api_v1_and_openapi.py` fails in the same case. The spec holds no
environment-dependent values.

## Authentication

Use a Bearer API key (see [API_KEYS.md](API_KEYS.md)). Keys need no `X-Requested-With` header.

```
export PSA=https://<your PSA host>/api/v1
export KEY=psa_xxxxxxxx
```

## Examples for the integration fields

Organization `uuid` and `rmm_client_id` (the uuid is read-only; set the RMM client id with a patch):

```
curl -H "Authorization: Bearer $KEY" $PSA/organizations/12
# {"id": 12, "uuid": "...", "rmm_client_id": null, ...}
curl -X PATCH -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"rmm_client_id": "ninja-42"}' $PSA/organizations/12
```

Create a ticket with `external_ref` (the source is recorded as `api`):

```
curl -X POST -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"organization_id": 12, "subject": "Disk alert", "external_ref": "RMM-1001"}' $PSA/tickets
```

Posting the same `external_ref` again returns 409 with the existing ticket:

```
HTTP/1.1 409 Conflict
{"detail": {"message": "external_ref already used", "ticket_id": 345}}
```

Log automation time with `entry_type` `automation` (never billable; reported separately as
`automation_minutes` in utilisation):

```
curl -X POST -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"work_type_id": 1, "minutes": 5, "entry_type": "automation", "note": "Patch script"}' \
  $PSA/tickets/345/time
```
