# Plan 14-01 Summary: Portal Entra SSO and the phase 14 schema

## Result
**Status**: Complete with Warnings
**Wave**: 1
**Agent**: engineering-security-engineer
**Completed**: 2026-10-31

## Agent Selection Rationale

| Candidate | Semantic | Heuristic | Memory | Total | Source |
|-----------|----------|-----------|--------|-------|--------|
| engineering-security-engineer | — | 13 | 0 | 13 | mandatory |
| engineering-senior-developer | — | 24 | 2.91 | 26.91 | heuristic |
| testing-api-tester | — | 17 | 3.3 | 20.3 | heuristic |

- **Task type detected**: implementation
- **Confidence**: LOW
- **Adapter**: claude-code
- **Model tier**: sonnet

## Completed Tasks
- [x] Task 1: Migration 0035 and models (done)
- [x] Task 2: Portal SSO flow (done)
- [x] Task 3: Staff tenant field, tests, docs and spec (done)

## Files Modified
- `.env.example`
- `backend/alembic/versions/0035_portal_polish.py`
- `backend/app/auth/oidc.py`
- `backend/app/config.py`
- `backend/app/models.py`
- `backend/app/portal_schemas.py`
- `backend/app/routers/organizations.py`
- `backend/app/routers/portal.py`
- `backend/app/schemas.py`
- `backend/app/services.py`
- `backend/tests/test_organizations.py`
- `backend/tests/test_portal_sso.py`
- `backend/tests/test_seed_and_migrations.py`
- `backend/tests/test_zz_api_contract.py`
- `docs/PORTAL.md`
- `docs/PORTAL_SSO.md`
- `docs/api/openapi.json`

## Verification Results
6/6 verification commands passed (run by Triad after the agent finished).

## Verification Commands
| Command | Exit Code | Result |
|---------|-----------|--------|
| `cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/python -m pytest -q tests/test_portal_sso.py tests/test_portal.py tests/test_auth.py tests/test_organizations.py tests/test_isolation.py tests/test_backup_restore.py tests/test_seed_and_migrations.py tests/test_api_v1_and_openapi.py tests/test_zz_api_contract.py` | 0 | PASS |
| `cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/python -W ignore -m app.openapi_export --check` | 0 | PASS |
| `cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/ruff check app tests && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/ruff format --check app tests` | 0 | PASS |
| `cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/python -m pytest -q tests/test_seed_and_migrations.py tests/test_isolation.py tests/test_backup_restore.py` | 0 | PASS |
| `cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/python -W ignore -c "from app.main import app; ps=app.openapi()['paths']; assert '/api/v1/portal/sso/login' in ps and '/api/v1/portal/sso/callback' in ps and '/api/v1/portal/login-options' in ps"` | 0 | PASS |
| `cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/python -m pytest -q tests/test_portal_sso.py tests/test_organizations.py` | 0 | PASS |

## Key Decisions
- no new grants: 0001 already gives psa_app table-wide UPDATE on contacts and organizations, and attachments keep SELECT, INSERT plus UPDATE (organization_id)

## Issues Encountered
(none)

## Escalations
| # | Severity | Type | Decision | Status | Resolution |
|---|----------|------|----------|--------|------------|
| 1 | info | security | Setting organizations.entra_tenant_id now needs portal:manage (admin) instead of org:write; clearing it does not. Unlinking a contact's Entra account also ends its portal sessions. | pending | INVALID: type "security" is not one of architecture, dependency, scope, schema, api, deletion, infrastructure, quality |

- #1 context: The tenant id decides which Microsoft accounts can sign in to a client's portal, so it carries the same risk as granting portal access, which is already admin-only. Plan 14-03 should hide or disable the tenant-id input for non-admins.

## Handoff Context
- **Key outputs**: .env.example; backend/alembic/versions/0035_portal_polish.py; backend/app/auth/oidc.py; backend/app/config.py; backend/app/models.py; backend/app/portal_schemas.py; backend/app/routers/organizations.py; backend/app/routers/portal.py; backend/app/schemas.py; backend/app/services.py; backend/tests/test_organizations.py; backend/tests/test_portal_sso.py; backend/tests/test_seed_and_migrations.py; backend/tests/test_zz_api_contract.py; docs/PORTAL.md; docs/PORTAL_SSO.md; docs/api/openapi.json
- **Decisions made**: no new grants: 0001 already gives psa_app table-wide UPDATE on contacts and organizations, and attachments keep SELECT, INSERT plus UPDATE (organization_id)
- **Open questions**: (none)
- **Conventions established**: Attachment.source defaults to 'email' in the database; portal uploads must set source='portal', uploaded_by_contact_id and email_message_id=None (the CHECK requires a message id for email rows)

## Requirements Covered
- REQ-13

## Token Usage
44 requests, 3640626 input tokens (3160653 cached), 38545 output tokens, $3.8028
