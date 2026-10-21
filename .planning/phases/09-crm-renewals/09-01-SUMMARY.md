# Plan 09-01 Summary: CRM schema, stages and permissions

## Result
**Status**: Complete
**Wave**: 1
**Agent**: engineering-backend-architect
**Completed**: 2026-10-21

## Agent Selection Rationale

| Candidate | Semantic | Heuristic | Memory | Total | Source |
|-----------|----------|-----------|--------|-------|--------|
| engineering-backend-architect | — | 15 | 3.29 | 18.29 | mandatory |
| engineering-senior-developer | — | 19 | 3.14 | 22.14 | heuristic |
| testing-qa-verification-specialist | — | 12 | 3.83 | 15.83 | heuristic |

- **Task type detected**: implementation
- **Confidence**: LOW
- **Adapter**: claude-code
- **Model tier**: sonnet

## Completed Tasks
- [x] Task 1: Migration 0030 and models (done)
- [x] Task 2: Permissions and schema tests (done)

## Files Modified
- `backend/alembic/versions/0030_crm.py`
- `backend/app/models.py`
- `backend/app/permissions.py`
- `backend/tests/conftest.py`
- `backend/tests/test_crm_schema.py`
- `backend/tests/test_permissions.py`

## Verification Results
5/5 verification commands passed (run by Triad after the agent finished).

## Verification Commands
| Command | Exit Code | Result |
|---------|-----------|--------|
| `service postgresql start >/dev/null 2>&1; cd backend && ruff check app tests && ruff format --check app tests` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_crm_schema.py tests/test_permissions.py tests/test_quoting.py tests/test_seed_and_migrations.py` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && alembic upgrade head && alembic downgrade 0029 && alembic upgrade head` | 0 | PASS |
| `cd backend && grep -q 'renewal_reminders, opportunities, opportunity_stages, leads' tests/conftest.py` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_crm_schema.py tests/test_permissions.py` | 0 | PASS |

## Key Decisions
- Added uq_quotes_id_org and uq_agreements_id_org in the migration, since neither table had a unique (id, organization_id) for the composite FKs. The downgrade drops them.
- Added a partial unique index uq_opportunity_stages_active_terminal, so at most one active won and one active lost stage can exist. The "at least one" half is left to the 09-02 service.
- leads and opportunity_stages have no RLS and get SELECT, INSERT and UPDATE for psa_app only. They have no DELETE.

## Issues Encountered
(none)

## Escalations
(none)

## Handoff Context
- **Key outputs**: backend/alembic/versions/0030_crm.py; backend/app/models.py; backend/app/permissions.py; backend/tests/conftest.py; backend/tests/test_crm_schema.py; backend/tests/test_permissions.py
- **Decisions made**: Added uq_quotes_id_org and uq_agreements_id_org in the migration, since neither table had a unique (id, organization_id) for the composite FKs. The downgrade drops them.; Added a partial unique index uq_opportunity_stages_active_terminal, so at most one active won and one active lost stage can exist. The "at least one" half is left to the 09-02 service.; leads and opportunity_stages have no RLS and get SELECT, INSERT and UPDATE for psa_app only. They have no DELETE.
- **Open questions**: (none)
- **Conventions established**: Constraint names to match in 09-02: ck_leads_status, ck_opportunity_stages_kind and _probability, ck_opportunities_kind, _monthly and _term, ck_renewal_reminders_lead_days and _status, and uq_renewal_reminders_once.; The reseeded stages get fresh ids after each TRUNCATE ... RESTART IDENTITY, so tests should look stages up by name or kind.; Opportunity.quote_id and agreement_id, and RenewalReminder.agreement_id and opportunity_id, are plain BigInteger columns in the models. The composite FKs exist only in the migration, as with the project tables.; Settings.renewal_reminder_days defaults to {90,30} and renewal_email to NULL.

## Requirements Covered
- REQ-09

## Token Usage
9 requests, 366446 input tokens (317285 cached), 14399 output tokens, $0.3303
