# Plan 19-03 Summary: Wizard steps: create, connect and verify registrations (backend)

## Result
**Status**: Complete with Warnings
**Wave**: 2
**Agent**: engineering-backend-architect
**Completed**: 2026-11-03

## Agent Selection Rationale

| Candidate | Semantic | Heuristic | Memory | Total | Source |
|-----------|----------|-----------|--------|-------|--------|
| engineering-backend-architect | — | 14 | 2.99 | 16.990000000000002 | mandatory |
| engineering-senior-developer | — | 25 | 3.07 | 28.07 | heuristic |
| testing-api-tester | — | 20 | 3.3 | 23.3 | heuristic |

- **Task type detected**: implementation
- **Confidence**: LOW
- **Adapter**: claude-code
- **Model tier**: sonnet

## Completed Tasks
- [x] Task 1: Create or connect registrations (done)
- [x] Task 2: Verify and finish (done)
- [x] Task 3: Tests (done)

## Files Modified
- `backend/app/onboarding.py`
- `backend/app/routers/onboarding.py`
- `backend/app/schemas.py`
- `backend/tests/test_onboarding.py`
- `docs/api/openapi.json`

## Verification Results
7/7 verification commands passed (run by Triad after the agent finished).

## Verification Commands
| Command | Exit Code | Result |
|---------|-----------|--------|
| `cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/ruff check app tests` | 0 | PASS |
| `cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/ruff format --check app tests` | 0 | PASS |
| `cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/python -m app.openapi_export --check` | 0 | PASS |
| `cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/pytest -q -p no:warnings tests/test_onboarding.py tests/test_onboarding_auth.py tests/test_keyvault.py tests/test_api_v1_and_openapi.py tests/test_zz_api_contract.py` | 0 | PASS |
| `cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/pytest -q -p no:warnings tests/test_onboarding.py -k 'create or connect'` | 0 | PASS |
| `cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/pytest -q -p no:warnings tests/test_onboarding.py -k 'verify or finish'` | 0 | PASS |
| `cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/pytest -q -p no:warnings tests/test_onboarding.py tests/test_zz_api_contract.py` | 0 | PASS |

## Key Decisions
- OnboardingError is a subclass of HTTPException, so main.py did not need a new handler; Graph 401 -> 409 "Sign in to Microsoft again"; other Graph or Key Vault failures -> 502 with a public message

## Issues Encountered
(none)

## Escalations
| # | Severity | Type | Decision | Status | Resolution |
|---|----------|------|----------|--------|------------|
| 1 | info | api_contract | POST /onboarding/connect takes an optional `mailbox` field beyond the plan's {kind, app_id}. A 409 from create returns {detail, app_id} (OnboardingAppExistsOut) instead of ErrorOut. connect refuses to store a secret while differences exist. | pending | INVALID: type "api_contract" is not one of architecture, dependency, scope, schema, api, deletion, infrastructure, quality |

- #1 context: The plan wants connect to fill the mail-mailbox secret and the PowerShell, which needs a mailbox. The plan also wants the duplicate-name 409 to carry the existing appId. Not storing a secret for an over-privileged app keeps least privilege.

## Handoff Context
- **Key outputs**: backend/app/onboarding.py; backend/app/routers/onboarding.py; backend/app/schemas.py; backend/tests/test_onboarding.py; docs/api/openapi.json
- **Decisions made**: OnboardingError is a subclass of HTTPException, so main.py did not need a new handler; Graph 401 -> 409 "Sign in to Microsoft again"; other Graph or Key Vault failures -> 502 with a public message
- **Open questions**: (none)
- **Conventions established**: Frontend: a 409 from POST /portal-app or /mail-app has the body {detail, app_id}; offer "connect" using that app_id

## Requirements Covered
- R19-2
- R19-3

## Token Usage
24 requests, 1288748 input tokens (1210354 cached), 33889 output tokens, $1.3118
