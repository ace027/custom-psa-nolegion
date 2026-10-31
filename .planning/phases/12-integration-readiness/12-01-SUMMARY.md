# Plan 12-01 Summary: Integration-readiness schema, models, schemas and writers

## Result
**Status**: Complete
**Wave**: 1
**Agent**: engineering-backend-architect
**Completed**: 2026-10-31

## Agent Selection Rationale

| Candidate | Semantic | Heuristic | Memory | Total | Source |
|-----------|----------|-----------|--------|-------|--------|
| engineering-backend-architect | — | 19 | 2.8 | 21.8 | mandatory |
| engineering-senior-developer | — | 20 | 2.83 | 22.83 | heuristic |
| testing-qa-verification-specialist | — | 13 | 3.08 | 16.08 | heuristic |

- **Task type detected**: implementation
- **Confidence**: LOW
- **Adapter**: claude-code
- **Model tier**: sonnet

## Completed Tasks
- [x] Task 1: Migration 0033 and models (done)
- [x] Task 2: Schemas and writers (done)
- [x] Task 3: Tests and docs (done)

## Files Modified
(none)

## Verification Results
7/7 verification commands passed (run by Triad after the agent finished).

## Verification Commands
| Command | Exit Code | Result |
|---------|-----------|--------|
| `service postgresql start >/dev/null 2>&1; cd backend && ruff check app tests && ruff format --check app tests` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_integration_readiness.py tests/test_seed_and_migrations.py tests/test_isolation.py tests/test_backup_restore.py tests/test_tickets.py tests/test_automation.py tests/test_events.py tests/test_webhooks.py` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_zz_api_contract.py tests/test_permissions.py` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_seed_and_migrations.py tests/test_isolation.py tests/test_backup_restore.py` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_tickets.py tests/test_automation.py tests/test_events.py tests/test_webhooks.py tests/test_zz_api_contract.py tests/test_permissions.py` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_integration_readiness.py tests/test_seed_and_migrations.py tests/test_isolation.py tests/test_backup_restore.py` | 0 | PASS |
| `grep -q 'rmm_client_id' docs/INTEGRATIONS.md` | 0 | PASS |

## Key Decisions
- Ticket source CHECK also keeps 'project' (set by app/projects.py since migration 0029) beside the six owner-approved values. The plan's list would have broken project tickets.
- Asset backfill: any asset with a source row becomes 'import', then any with a NinjaOne (kind 'ninjaone') source becomes 'rmm', so NinjaOne wins.
- Rule conditions are rewritten in Python, handling both a single value and a list value, in both directions.
- Note source values ('ui') are unchanged, because they are a separate enum from ticket source.

## Issues Encountered
(none)

## Escalations
(none)

## Handoff Context
- **Key outputs**: (none)
- **Decisions made**: Ticket source CHECK also keeps 'project' (set by app/projects.py since migration 0029) beside the six owner-approved values. The plan's list would have broken project tickets.; Asset backfill: any asset with a source row becomes 'import', then any with a NinjaOne (kind 'ninjaone') source becomes 'rmm', so NinjaOne wins.; Rule conditions are rewritten in Python, handling both a single value and a list value, in both directions.; Note source values ('ui') are unchanged, because they are a separate enum from ticket source.
- **Open questions**: (none)
- **Conventions established**: Next wave can rely on /api responses carrying uuid on organizations, sites and contacts, and rmm_client_id on organizations.; Next wave can rely on source and external_id on assets, and source and external_ref on tickets.; Next wave can rely on author_type on notes, entry_type on time entries, and entra_tenant_id on users.; Reports must treat entry_type 'automation' as a separate column.; Billing already excludes automation rows because the CHECK forces billable=false.; Phase 14 can reuse users.entra_oid together with entra_tenant_id.

## Requirements Covered
- REQ-14

## Token Usage
7 requests, 184223 input tokens (159741 cached), 3206 output tokens, $0.1252
