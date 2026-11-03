# Plan 17-02 Summary: Billing by agreement: all-inclusive and block rollover

## Result
**Status**: Complete with Warnings
**Wave**: 2
**Agent**: engineering-backend-architect
**Completed**: 2026-11-03

## Agent Selection Rationale

| Candidate | Semantic | Heuristic | Memory | Total | Source |
|-----------|----------|-----------|--------|-------|--------|
| engineering-backend-architect | — | 8 | 3.04 | 11.04 | mandatory |
| engineering-senior-developer | — | 17 | 3.02 | 20.02 | heuristic |
| testing-qa-verification-specialist | — | 12 | 3.13 | 15.129999999999999 | heuristic |

- **Task type detected**: implementation
- **Confidence**: LOW
- **Adapter**: claude-code
- **Model tier**: sonnet

## Completed Tasks
- [x] Task 1: All-inclusive and attachment-aware selection (done)
- [x] Task 2: Rollover (done)
- [x] Task 3: Exact-cent tests and docs (done)

## Files Modified
- `backend/app/billing.py`
- `backend/app/billing_repo.py`
- `backend/tests/test_agreement_billing.py`
- `docs/BILLING.md`

## Verification Results
6/6 verification commands passed (run by Triad after the agent finished).

## Verification Commands
| Command | Exit Code | Result |
|---------|-----------|--------|
| `cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/ruff check app tests` | 0 | PASS |
| `cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/ruff format --check app tests` | 0 | PASS |
| `cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/pytest -q -p no:warnings tests/test_agreement_billing.py tests/test_block_billing.py tests/test_block_agreements.py tests/test_billing_runs.py tests/test_billing_db_guards.py tests/test_agreement_attachment.py` | 0 | PASS |
| `cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/pytest -q -p no:warnings tests/test_block_billing.py tests/test_billing_runs.py tests/test_block_agreements.py` | 0 | PASS |
| `cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/pytest -q -p no:warnings tests/test_agreement_billing.py tests/test_block_billing.py` | 0 | PASS |
| `cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/pytest -q -p no:warnings tests/test_agreement_billing.py` | 0 | PASS |

## Key Decisions
- Carried-in minutes are shown in hours, like the existing line: "N h included (incl. C h carried over)". The note appears only when the carry-in is above 0, so expire runs and runs with nothing carried print the same text as before.

## Issues Encountered
- The shared psa_test DB deadlocks and gives 401s when 17-03 runs tests at the same time. I ran on a separate DB I created myself (psa_test_1702, now dropped). Triad should run the plan's commands without the other wave running, or set PSA_TEST_DB_NAME.

## Escalations
| # | Severity | Type | Decision | Status | Resolution |
|---|----------|------|----------|--------|------------|
| 1 | info | quality-gate | The plan's `ruff check app tests` gate fails because of E501 in backend/app/routers/reports.py:295, which belongs to plan 17-03. | pending | INVALID: type "quality-gate" is not one of architecture, dependency, scope, schema, api, deletion, infrastructure, quality |

- #1 context: That file is forbidden to me. 17-03 needs to shorten the `summary=` string before the combined gate passes.

## Handoff Context
- **Key outputs**: backend/app/billing.py; backend/app/billing_repo.py; backend/tests/test_agreement_billing.py; docs/BILLING.md
- **Decisions made**: Carried-in minutes are shown in hours, like the existing line: "N h included (incl. C h carried over)". The note appears only when the carry-in is above 0, so expire runs and runs with nothing carried print the same text as before.
- **Open questions**: (none)
- **Conventions established**: `block_candidates` now takes `(db, scope, agreement, start, end)` instead of org_id; `_pull_block` is its only caller.

## Requirements Covered
- P01-01 note
- Block-hour rollover configurable

## Token Usage
29 requests, 2057782 input tokens (1960756 cached), 26514 output tokens, $1.4075
