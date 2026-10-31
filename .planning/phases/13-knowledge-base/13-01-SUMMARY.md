# Plan 13-01 Summary: Knowledge base backend: schema, permissions, staff, suggestion and portal APIs

## Result
**Status**: Partial
**Wave**: 1
**Agent**: engineering-backend-architect
**Completed**: 2026-10-31
**Failure Class**: BLOCKER — tests/test_seed_and_migrations.py:49: AssertionError

## Agent Selection Rationale

| Candidate | Semantic | Heuristic | Memory | Total | Source |
|-----------|----------|-----------|--------|-------|--------|
| engineering-backend-architect | — | 13 | 2.89 | 15.89 | mandatory |
| engineering-senior-developer | — | 20 | 2.91 | 22.91 | heuristic |
| testing-api-tester | — | 16 | 3.3 | 19.3 | heuristic |

- **Task type detected**: implementation
- **Confidence**: LOW
- **Adapter**: claude-code
- **Model tier**: sonnet

## Completed Tasks
- [x] Task 1: Migration, model and permissions (done)
- [x] Task 2: Service, schemas and staff + portal routes (done)
- [ ] Task 3: Tests, seed and OpenAPI spec (partial)

## Files Modified
- `backend/alembic/versions/0034_knowledge_base.py`
- `backend/app/kb.py`
- `backend/app/kb_schemas.py`
- `backend/app/main.py`
- `backend/app/models.py`
- `backend/app/permissions.py`
- `backend/app/routers/kb.py`
- `backend/app/routers/portal.py`
- `backend/app/seed.py`
- `backend/tests/test_kb.py`
- `backend/tests/test_kb_portal.py`
- `backend/tests/test_permissions.py`
- `docs/api/openapi.json`

## Verification Results
3/6 verification commands passed (run by Triad after the agent finished).

## Verification Commands
| Command | Exit Code | Result |
|---------|-----------|--------|
| `cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/python -m pytest -q tests/test_kb.py tests/test_kb_portal.py tests/test_permissions.py tests/test_isolation.py tests/test_backup_restore.py tests/test_seed_and_migrations.py tests/test_portal.py tests/test_api_v1_and_openapi.py tests/test_zz_api_contract.py` | 1 | FAIL |
| `cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/python -m app.openapi_export --check` | 0 | PASS |
| `cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/ruff check app tests && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/ruff format --check app tests` | 0 | PASS |
| `cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/python -m pytest -q tests/test_permissions.py tests/test_isolation.py tests/test_seed_and_migrations.py` | 1 | FAIL |
| `cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/python -c "from app.main import app; ps={r.path for r in app.routes}; assert '/api/v1/kb/articles' in ps and '/api/v1/kb/suggestions' in ps and '/api/v1/portal/kb' in ps"` | 1 | FAIL |
| `cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/python -m pytest -q tests/test_kb.py tests/test_kb_portal.py` | 0 | PASS |

## Key Decisions
- `search` is popped from audit snapshots because it is a derived tsvector.
- A tag list over 10 items is rejected before de-duplication, so 11 raw tags give 422.
- `seed_knowledge` runs in both seed branches and skips when articles already exist.
- Null values for non-null fields in a PATCH are ignored.

## Issues Encountered
- The `"0033"` assertion described above is a stale test outside my write list.
- The plan's route-check one-liner is broken for this FastAPI version, as noted above.
- BLOCKER: tests/test_seed_and_migrations.py:49: AssertionError

## Escalations
| # | Severity | Type | Decision | Status | Resolution |
|---|----------|------|----------|--------|------------|
| 1 | blocker | out-of-scope file | Allow a one-line edit in backend/tests/test_seed_and_migrations.py (line 49, `"0033"` to `"0034"`), or give another way to satisfy that test | pending | INVALID: type "out-of-scope file" is not one of architecture, dependency, scope, schema, api, deletion, infrastructure, quality |
| 2 | blocker | schema | Resolve: tests/test_seed_and_migrations.py:49: AssertionError | pending |  |

- #1 context: Adding migration 0034 as required makes the existing head-version assertion fail. The file is not in files_modified, so I left it unchanged. The plan's verification command cannot reach exit 0 without this edit.
- #2 context: Verification failed (cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/python -m pytest -q tests/test_kb.py tests/test_kb_portal.py tests/test_permissions.py tests/test_isolation.py tests/test_backup_restore.py tests/test_seed_and_migrations.py tests/test_portal.py tests/test_api_v1_and_openapi.py tests/test_zz_api_contract.py; cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/python -m pytest -q tests/test_permissions.py tests/test_isolation.py tests/test_seed_and_migrations.py; cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/python -c "from app.main import app; ps={r.path for r in app.routes}; assert '/api/v1/kb/articles' in ps and '/api/v1/kb/suggestions' in ps and '/api/v1/portal/kb' in ps"); a BLOCKER is not auto-fixed.

## Handoff Context
- **Key outputs**: backend/alembic/versions/0034_knowledge_base.py; backend/app/kb.py; backend/app/kb_schemas.py; backend/app/main.py; backend/app/models.py; backend/app/permissions.py; backend/app/routers/kb.py; backend/app/routers/portal.py; backend/app/seed.py; backend/tests/test_kb.py; backend/tests/test_kb_portal.py; backend/tests/test_permissions.py; docs/api/openapi.json
- **Decisions made**: `search` is popped from audit snapshots because it is a derived tsvector.; A tag list over 10 items is rejected before de-duplication, so 11 raw tags give 422.; `seed_knowledge` runs in both seed branches and skips when articles already exist.; Null values for non-null fields in a PATCH are ignored.
- **Open questions**: (none)
- **Conventions established**: Frontend routes: `GET/POST /api/v1/kb/articles`, `GET/PATCH /api/v1/kb/articles/{id}`, `GET /api/v1/kb/suggestions?ticket_id=`, `GET /api/v1/portal/kb?q=` and `GET /api/v1/portal/kb/{id}`.; `q` must be 2 to 100 characters. Staff list returns `Page[KbArticleSummary]` with `limit` 1 to 100, default 25.; Portal responses omit status, visibility and author names. Hidden articles return 404.; Suggestions return published articles of either visibility, at most 5.

## Requirements Covered
- REQ-12

### Failed verification output
`cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/python -m pytest -q tests/test_kb.py tests/test_kb_portal.py tests/test_permissions.py tests/test_isolation.py tests/test_backup_restore.py tests/test_seed_and_migrations.py tests/test_portal.py tests/test_api_v1_and_openapi.py tests/test_zz_api_contract.py`
```
^
E             + 0034
E             ?    ^

tests/test_seed_and_migrations.py:49: AssertionError
=============================== warnings summary ===============================
../../../../tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/lib/python3.12/site-packages/fastapi/testclient.py:1
  /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/lib/python3.12/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

../../../../tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/lib/python3.12/site-packages/authlib/integrations/httpx_client/assertion_client.py:5
  /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/lib/python3.12/site-packages/authlib/integrations/httpx_client/assertion_client.py:5: AuthlibDeprecationWarning: The httpx module is deprecated; please use httpx2 instead.
    from ._compat import httpx2

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED tests/test_seed_and_migrations.py::test_migration_0032_reporting_tables_and_constraints
1 failed, 88 passed, 1 skipped, 2 warnings in 73.95s (0:01:13)

```
`cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/python -m pytest -q tests/test_permissions.py tests/test_isolation.py tests/test_seed_and_migrations.py`
```
3
E             ?    ^
E             + 0034
E             ?    ^

tests/test_seed_and_migrations.py:49: AssertionError
=============================== warnings summary ===============================
../../../../tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/lib/python3.12/site-packages/fastapi/testclient.py:1
  /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/lib/python3.12/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

../../../../tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/lib/python3.12/site-packages/authlib/integrations/httpx_client/assertion_client.py:5
  /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/lib/python3.12/site-packages/authlib/integrations/httpx_client/assertion_client.py:5: AuthlibDeprecationWarning: The httpx module is deprecated; please use httpx2 instead.
    from ._compat import httpx2

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED tests/test_seed_and_migrations.py::test_migration_0032_reporting_tables_and_constraints
1 failed, 32 passed, 2 warnings in 29.45s

```
`cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/python -c "from app.main import app; ps={r.path for r in app.routes}; assert '/api/v1/kb/articles' in ps and '/api/v1/kb/suggestions' in ps and '/api/v1/portal/kb' in ps"`
```
/tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/lib/python3.12/site-packages/authlib/integrations/httpx_client/assertion_client.py:5: AuthlibDeprecationWarning: The httpx module is deprecated; please use httpx2 instead.
  from ._compat import httpx2
Traceback (most recent call last):
  File "<string>", line 1, in <module>
AttributeError: '_IncludedRouter' object has no attribute 'path'

```

## Token Usage
17 requests, 785527 input tokens (718692 cached), 21279 output tokens, $0.5236
