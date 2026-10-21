# Plan 07-02 Summary: API keys: hashed, scoped, revocable bearer auth

## Result
**Status**: Complete
**Wave**: 2
**Agent**: engineering-security-engineer
**Completed**: 2026-10-21

## Agent Selection Rationale

| Candidate | Semantic | Heuristic | Memory | Total | Source |
|-----------|----------|-----------|--------|-------|--------|
| engineering-security-engineer | — | 10 | 0 | 10 | mandatory |
| engineering-senior-developer | — | 22 | 3.08 | 25.08 | heuristic |
| engineering-backend-architect | — | 18 | 3.01 | 21.009999999999998 | heuristic |

- **Task type detected**: implementation
- **Confidence**: LOW
- **Adapter**: claude-code
- **Model tier**: sonnet

## Completed Tasks
- [x] Task 1: Key service and auth path (done)
- [x] Task 2: Routes and backend tests (done)
- [x] Task 3: API keys page (done)

## Files Modified
- `backend/app/api_keys.py`
- `backend/app/audit.py`
- `backend/app/context.py`
- `backend/app/deps.py`
- `backend/app/main.py`
- `backend/app/routers/api_keys.py`
- `backend/app/schemas.py`
- `backend/tests/test_api_keys.py`
- `docs/API_KEYS.md`
- `frontend/src/ApiKeys.test.tsx`
- `frontend/src/App.tsx`
- `frontend/src/api.ts`
- `frontend/src/pages/ApiKeys.tsx`

## Verification Results
6/6 verification commands passed (run by Triad after the agent finished).

## Verification Commands
| Command | Exit Code | Result |
|---------|-----------|--------|
| `service postgresql start >/dev/null 2>&1; cd backend && ruff check app tests && ruff format --check app tests` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_api_keys.py tests/test_auth.py tests/test_permissions.py tests/test_audit.py tests/test_tickets.py` | 0 | PASS |
| `cd frontend && npm run typecheck && npx vitest run && npm run build` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -c 'import app.main'` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_api_keys.py tests/test_auth.py` | 0 | PASS |
| `cd frontend && npm run typecheck && npx vitest run src/ApiKeys.test.tsx` | 0 | PASS |

## Key Decisions
- Sync FastAPI dependencies and handlers run in separate thread contexts, so a ContextVar set in the dependency never reached the handler. The key id is also stored in `db.info["api_key_id"]`, and `audit.record` reads that first, then `api_key_id_var`.
- The dependency commits right after a successful `authenticate`, so the throttled `last_used_at` update is kept even when the request is then refused with 403.
- A rejected key leaves one `auth.api_key_rejected` audit row. It holds only the 8-character prefix, never the token.

## Issues Encountered
(none)

## Escalations
(none)

## Handoff Context
- **Key outputs**: backend/app/api_keys.py; backend/app/audit.py; backend/app/context.py; backend/app/deps.py; backend/app/main.py; backend/app/routers/api_keys.py; backend/app/schemas.py; backend/tests/test_api_keys.py; docs/API_KEYS.md; frontend/src/ApiKeys.test.tsx; frontend/src/App.tsx; frontend/src/api.ts; frontend/src/pages/ApiKeys.tsx
- **Decisions made**: Sync FastAPI dependencies and handlers run in separate thread contexts, so a ContextVar set in the dependency never reached the handler. The key id is also stored in `db.info["api_key_id"]`, and `audit.record` reads that first, then `api_key_id_var`.; The dependency commits right after a successful `authenticate`, so the throttled `last_used_at` update is kept even when the request is then refused with 403.; A rejected key leaves one `auth.api_key_rejected` audit row. It holds only the 8-character prefix, never the token.
- **Open questions**: (none)
- **Conventions established**: Later code can read `ctx.api_key_id` and `db.info["api_key_id"]` to tell whether a request came from an API key.; Handlers that use `authenticated()` refuse API keys with 403, so any new endpoint a key should reach needs `require(<perm>)`.; Keys can only be granted permissions that appear in MATRIX and are not in `KEY_FORBIDDEN`.; `authenticate()` only flushes; the caller must commit.

## Requirements Covered
- REQ-07

## Token Usage
15 requests, 766910 input tokens (705255 cached), 18819 output tokens, $0.4834
