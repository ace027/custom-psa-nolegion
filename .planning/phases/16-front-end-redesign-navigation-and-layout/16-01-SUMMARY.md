# Plan 16-01 Summary: Permission split and manager role

## Result
**Status**: Partial
**Wave**: 1
**Agent**: engineering-security-engineer
**Completed**: 2026-11-02

## Agent Selection Rationale

| Candidate | Semantic | Heuristic | Memory | Total | Source |
|-----------|----------|-----------|--------|-------|--------|
| engineering-security-engineer | — | 13 | 2.53 | 15.53 | mandatory |
| engineering-senior-developer | — | 25 | 2.97 | 27.97 | heuristic |
| testing-api-tester | — | 22 | 3.3 | 25.3 | heuristic |

- **Task type detected**: implementation
- **Confidence**: LOW
- **Adapter**: claude-code
- **Model tier**: sonnet

## Completed Tasks
- [x] Task 1: Permission split and roles (done)
- [x] Task 2: Manager role in the database, users API and UI gates (done)
- [ ] Task 3: Role-by-endpoint test matrix (partial)

## Files Modified
(none)

## Verification Results
8/8 verification commands passed (run by Triad after the agent finished).

## Verification Commands
| Command | Exit Code | Result |
|---------|-----------|--------|
| `cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/ruff check app tests` | 0 | PASS |
| `cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/python -m app.openapi_export --check` | 0 | PASS |
| `cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/pytest -q -p no:warnings` | 0 | PASS |
| `cd frontend && npm run -s typecheck && npx vitest run` | 0 | PASS |
| `cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/python -c "from app import permissions as P; assert 'manager' in P.ROLES; m=P.MATRIX; assert 'invoice:read' not in m['tech'] and 'procurement:read' not in m['tech'] and 'procurement:read' not in m['read_only']; assert {'invoice:read','service:configure','report:read','audit:read','timesheet:approve'} <= m['manager']; assert 'config:manage' not in m['manager'] and 'billing:finalize' not in m['manager']"` | 0 | PASS |
| `cd backend && grep -q "manager" alembic/versions/0039_manager_role_and_permission_split.py` | 0 | PASS |
| `cd frontend && npm run -s typecheck` | 0 | PASS |
| `cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/pytest -q -p no:warnings tests/test_role_matrix.py tests/test_seed_and_migrations.py tests/test_zz_api_contract.py` | 0 | PASS |

## Key Decisions
- The client billing card is hidden as a whole without `invoice:read`, because routes that mix catalog and invoice data use `invoice:read`.

## Issues Encountered
- The full backend pytest suite is slow here (over 30 minutes) and did not finish within the time budget.

## Escalations
| # | Severity | Type | Decision | Status | Resolution |
|---|----------|------|----------|--------|------------|
| 1 | warning | quality-gate | Run the full backend pytest suite and the three-file Task 3 command with no time limit before committing. | pending | INVALID: type "quality-gate" is not one of architecture, dependency, scope, schema, api, deletion, infrastructure, quality |

- #1 context: The suite was still running when the time budget ran out and I got no result, so the full backend run and the Task 3 command are unverified. Everything else passed: ruff, the openapi check, the frontend typecheck, vitest (340/340) and the Task 1 and 2 checks.

## Handoff Context
- **Key outputs**: (none)
- **Decisions made**: The client billing card is hidden as a whole without `invoice:read`, because routes that mix catalog and invoice data use `invoice:read`.
- **Open questions**: (none)
- **Conventions established**: Front-end navigation should gate finance on `invoice:read`, procurement on `procurement:read` and service settings on `service:configure`; manager is a valid role in the API, the database and the Users page.

## Requirements Covered
(none)

## Token Usage
19 requests, 632029 input tokens (490178 cached), 7081 output tokens, $0.9489
