# Plan 17-01 Summary: Agreement on tickets and time entries

## Result
**Status**: Complete with Warnings
**Wave**: 1
**Agent**: engineering-backend-architect
**Completed**: 2026-11-03

## Agent Selection Rationale

| Candidate | Semantic | Heuristic | Memory | Total | Source |
|-----------|----------|-----------|--------|-------|--------|
| engineering-backend-architect | — | 12 | 3.04 | 15.04 | mandatory |
| engineering-senior-developer | — | 19 | 3.02 | 22.02 | heuristic |
| testing-api-tester | — | 16 | 3.3 | 19.3 | heuristic |

- **Task type detected**: implementation
- **Confidence**: LOW
- **Adapter**: claude-code
- **Model tier**: sonnet

## Completed Tasks
- [x] Task 1: Migration and models (done)
- [x] Task 2: Defaulting, override and agreement settings (done)
- [x] Task 3: Tests and OpenAPI (done)

## Files Modified
- `backend/alembic/versions/0041_agreement_attachment_and_rollover.py`
- `backend/app/billing.py`
- `backend/app/models.py`
- `backend/app/routers/billing.py`
- `backend/app/routers/tickets.py`
- `backend/app/schemas.py`
- `backend/app/ticket_services.py`
- `backend/tests/test_agreement_attachment.py`
- `backend/tests/test_seed_and_migrations.py`
- `docs/api/openapi.json`

## Verification Results
7/7 verification commands passed (run by Triad after the agent finished).

## Verification Commands
| Command | Exit Code | Result |
|---------|-----------|--------|
| `cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/ruff check app tests` | 0 | PASS |
| `cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/ruff format --check app tests` | 0 | PASS |
| `cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/python -m app.openapi_export --check` | 0 | PASS |
| `cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/pytest -q -p no:warnings tests/test_agreement_attachment.py tests/test_seed_and_migrations.py tests/test_block_agreements.py tests/test_block_billing.py tests/test_billing_runs.py tests/test_tickets.py tests/test_permissions.py` | 0 | PASS |
| `cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/pytest -q -p no:warnings tests/test_seed_and_migrations.py` | 0 | PASS |
| `cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/pytest -q -p no:warnings tests/test_agreement_attachment.py tests/test_block_agreements.py tests/test_tickets.py` | 0 | PASS |
| `cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/ruff check app tests && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/ruff format --check app tests` | 0 | PASS |

## Key Decisions
- Leaving `agreement_id` out of a create request uses the default (the ticket's agreement, for time); sending null explicitly means no agreement.

## Issues Encountered
- TicketOut is built in app/ticket_views.py, which is not on my file list. I fill `agreement_id` in routers/tickets.py `_view` instead, which covers the ticket, dashboard and ticket-link endpoints. The project ticket endpoints (routers/projects.py) still return null for it. There is a `shortcut:` comment at that spot.

## Escalations
| # | Severity | Type | Decision | Status | Resolution |
|---|----------|------|----------|--------|------------|
| 1 | warning | out-of-scope-file | Approve a one-line change to backend/app/ticket_views.py, adding `agreement_id=t.agreement_id` to ticket_out, then remove the `model_copy` workaround in routers/tickets.py `_view`. | pending | INVALID: type "out-of-scope-file" is not one of architecture, dependency, scope, schema, api, deletion, infrastructure, quality |

- #1 context: TicketOut is only built in ticket_views.ticket_out. Without this change, the project ticket endpoints (routers/projects.py) report agreement_id as null even when it is set. Plan 17-04 (UI) may read tickets from those endpoints.

## Handoff Context
- **Key outputs**: backend/alembic/versions/0041_agreement_attachment_and_rollover.py; backend/app/billing.py; backend/app/models.py; backend/app/routers/billing.py; backend/app/routers/tickets.py; backend/app/schemas.py; backend/app/ticket_services.py; backend/tests/test_agreement_attachment.py; backend/tests/test_seed_and_migrations.py; docs/api/openapi.json
- **Decisions made**: Leaving `agreement_id` out of a create request uses the default (the ticket's agreement, for time); sending null explicitly means no agreement.
- **Open questions**: (none)
- **Conventions established**: tickets.agreement_id and time_entries.agreement_id are nullable FKs (indexes ix_tickets_agreement_id, ix_time_entries_agreement_id); null means today's billing behaviour.

## Requirements Covered
- Owner test note 8

## Token Usage
42 requests, 2841062 input tokens (2737204 cached), 29007 output tokens, $1.6468
