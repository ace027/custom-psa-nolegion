# Plan 05-03 Summary: On-call API and portal appointments

## Result
**Status**: BLOCKED
**Wave**: 2
**Agent**: engineering-senior-developer
**Completed**: 2026-10-15
**Failure Class**: BLOCKER — $ service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_oncall_api.py (exit 4)

## Agent Selection Rationale

| Candidate | Semantic | Heuristic | Memory | Total | Source |
|-----------|----------|-----------|--------|-------|--------|
| engineering-senior-developer | — | 19 | 3.78 | 22.78 | heuristic |
| engineering-backend-architect | — | 14 | 3.6 | 17.6 | heuristic |
| testing-qa-verification-specialist | — | 12 | 4.38 | 16.38 | heuristic |

- **Task type detected**: implementation
- **Confidence**: HIGH
- **Adapter**: claude-code
- **Model tier**: sonnet

## Completed Tasks
- [ ] Task 1: On-call service and router (skipped)
- [ ] Task 2: Portal appointments (skipped)
- [ ] Task 3: Tests (skipped)

## Files Modified
(none)

## Verification Results
2/5 verification commands passed (run by Triad after the agent finished).

## Verification Commands
| Command | Exit Code | Result |
|---------|-----------|--------|
| `service postgresql start >/dev/null 2>&1; cd backend && ruff check app tests && ruff format --check app tests` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_oncall_api.py` | 4 | FAIL |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_portal_appointments.py` | 4 | FAIL |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_oncall_api.py tests/test_portal_appointments.py tests/test_portal.py tests/test_zz_api_contract.py` | 4 | FAIL |

## Key Decisions
(none)

## Issues Encountered
- `RotationCreate` and `OverrideCreate` in `backend/app/oncall_schemas.py` have no `organization_id`. `backend/app/oncall_schemas.py`, `backend/app/models.py` and `backend/alembic/` are forbidden to me.
- Staff requests run with `Scope.all()`, and there is no home or internal organization concept: `Settings` has no org column and `Organization` has no internal flag.
- "404 for ids outside the org" in Task 1 has no defined meaning when staff see every client.
- Everything else in the plan is resolvable from the existing code.
- Blocked: The plan does not say how a rotation gets its organization_id. I will not guess a source for it, because the choice shapes the RLS behavior and the API contract that plan 05-04 will build on.
- BLOCKER: $ service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_oncall_api.py (exit 4)

## Escalations
| # | Severity | Type | Decision | Status | Resolution |
|---|----------|------|----------|--------|------------|
| 1 | blocker | schema | Choose how a rotation, member or override gets its organization_id. I have listed the options in the order I would rank them. | approved | Owner chose staff-only: oncall_* tables have no organization_id and no RLS (like user_time_off), guarded by schedule:read/write. Migration 0026, models and schema tests updated on the main model; 05-03 plan text updated (404 = unknown id). |
| 2 | blocker | api | Resolve: $ service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_oncall_api.py (exit 4) | approved | Verification failed only because 05-03 stopped before writing tests (exit 4 = no test file). Unblocked by the decision in #1; re-run the build. |

- #1 context: / (a) Add an optional organization_id to RotationCreate and RotationOut (touches the forbidden oncall_schemas.py), and have 404 mean the rotation's org is not visible. This makes on-call per client. It does not fit "who is on call now" for a small MSP. (b) Add a nullable or home-organization concept through a new migration that drops NOT NULL on organization_id and changes the RLS policy (touches the forbidden alembic/ and models.py). This is the cleanest fit for an MSP-wide rotation. (c) Treat a designated organization as the MSP's own, for example the lowest-id organization or a settings value. This needs a new setting, so it is a schema change too. After you decide, 05-03 needs the forbidden-file edits from the chosen option, or an explicit okay for me to write that source into oncall_service.py (for example a constant lookup).
- #2 context: Verification failed (service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_oncall_api.py; service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_portal_appointments.py; service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_oncall_api.py tests/test_portal_appointments.py tests/test_portal.py tests/test_zz_api_contract.py); a BLOCKER is not auto-fixed.

## Handoff Context
- **Key outputs**: (none)
- **Decisions made**: (none)
- **Open questions**: (none)
- **Conventions established**: (none)

## Requirements Covered
- REQ-05

### Failed verification output
`service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_oncall_api.py`
```

no tests ran in 0.00s
ERROR: file or directory not found: tests/test_oncall_api.py


```
`service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_portal_appointments.py`
```

no tests ran in 0.00s
ERROR: file or directory not found: tests/test_portal_appointments.py


```
`service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_oncall_api.py tests/test_portal_appointments.py tests/test_portal.py tests/test_zz_api_contract.py`
```

no tests ran in 0.00s
ERROR: file or directory not found: tests/test_oncall_api.py


```

## Token Usage
11 requests, 520140 input tokens (453445 cached), 3972 output tokens, $0.2971
