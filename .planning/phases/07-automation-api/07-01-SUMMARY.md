# Plan 07-01 Summary: Automation & API schema, models and permissions

## Result
**Status**: Complete
**Wave**: 1
**Agent**: engineering-backend-architect
**Completed**: 2026-10-21

## Agent Selection Rationale

| Candidate | Semantic | Heuristic | Memory | Total | Source |
|-----------|----------|-----------|--------|-------|--------|
| engineering-backend-architect | — | 18 | 3.01 | 21.009999999999998 | mandatory |
| engineering-senior-developer | — | 23 | 3.08 | 26.08 | heuristic |
| testing-qa-verification-specialist | — | 12 | 3.61 | 15.61 | heuristic |

- **Task type detected**: implementation
- **Confidence**: LOW
- **Adapter**: claude-code
- **Model tier**: sonnet

## Completed Tasks
- [x] Task 1: Migration 0028 and models (done)
- [x] Task 2: Permissions (done)
- [x] Task 3: Schema tests (done)

## Files Modified
- `backend/alembic/versions/0028_automation_api.py`
- `backend/app/models.py`
- `backend/app/permissions.py`
- `backend/tests/conftest.py`
- `backend/tests/test_automation_schema.py`
- `backend/tests/test_permissions.py`

## Verification Results
6/6 verification commands passed (run by Triad after the agent finished).

## Verification Commands
| Command | Exit Code | Result |
|---------|-----------|--------|
| `service postgresql start >/dev/null 2>&1; cd backend && ruff check app tests && ruff format --check app tests` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_automation_schema.py tests/test_permissions.py tests/test_rmm_alerts_schema.py tests/test_tickets.py` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && alembic upgrade head && alembic downgrade 0027 && alembic upgrade head` | 0 | PASS |
| `cd backend && grep -q 'automation_runs, automation_rules, webhook_deliveries, webhook_endpoints, api_keys' tests/conftest.py` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_permissions.py` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_automation_schema.py` | 0 | PASS |

## Key Decisions
- The `ApiKey.user` relationship sets `foreign_keys=[user_id]` because the table has two FKs to users.
- `automation_rules` gets two CHECKs beyond the plan: `trigger <> ''` and `fire_count >= 0`.
- The migration grants `USAGE, SELECT` on all sequences, as the plan said for sequences.
- Schema tests insert a real staff user through a fixture, because `users` has no seeded id 1.

## Issues Encountered
- I did not re-run `test_rmm_alerts_schema.py` and `test_tickets.py` after the test fixture fix. Only the two automation and permission files changed after that run.

## Escalations
(none)

## Handoff Context
- **Key outputs**: backend/alembic/versions/0028_automation_api.py; backend/app/models.py; backend/app/permissions.py; backend/tests/conftest.py; backend/tests/test_automation_schema.py; backend/tests/test_permissions.py
- **Decisions made**: The `ApiKey.user` relationship sets `foreign_keys=[user_id]` because the table has two FKs to users.; `automation_rules` gets two CHECKs beyond the plan: `trigger <> ''` and `fire_count >= 0`.; The migration grants `USAGE, SELECT` on all sequences, as the plan said for sequences.; Schema tests insert a real staff user through a fixture, because `users` has no seeded id 1.
- **Open questions**: (none)
- **Conventions established**: Webhook delivery and automation-run uniqueness is enforced by `uq_webhook_deliveries_event` and the partial index `uq_automation_runs_event` (`WHERE NOT dry_run`). Later code can rely on `ON CONFLICT` against them.; `psa_app` has no DELETE on the new tables, so archive or revoke by setting columns such as `archived_at` and `revoked_at`.; Ticket source `'rule'` is allowed. The `Ticket.source` column is String(10), which fits.

## Requirements Covered
- REQ-07

## Token Usage
8 requests, 260483 input tokens (217116 cached), 13789 output tokens, $0.2897
