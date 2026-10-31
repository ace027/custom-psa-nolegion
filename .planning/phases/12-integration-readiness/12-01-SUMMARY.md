# Plan 12-01 Summary: Integration-readiness schema, models, schemas and writers

## Result
**Status**: Partial
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
- `backend/alembic/versions/0033_integration_readiness.py`
- `backend/app/asset_schemas.py`
- `backend/app/asset_sync.py`
- `backend/app/assets.py`
- `backend/app/auth/oidc.py`
- `backend/app/automation.py`
- `backend/app/models.py`
- `backend/app/repositories.py`
- `backend/app/routers/tickets.py`
- `backend/app/schemas.py`
- `backend/app/services.py`
- `backend/app/ticket_services.py`
- `backend/app/ticket_views.py`
- `backend/tests/test_automation.py`
- `backend/tests/test_events.py`
- `backend/tests/test_integration_readiness.py`
- `backend/tests/test_seed_and_migrations.py`
- `backend/tests/test_tickets.py`
- `backend/tests/test_webhooks.py`
- `docs/INTEGRATIONS.md`

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
- Kept `project` in the ticket source CHECK and in the `TicketSource` Literal. `app/projects.py` (not in my file list) creates tickets with source `project`, and the plan's six values would break it and its tests.
- Note `source` (`ui`/`email`) is a separate column with its own CHECK, so I left it alone. The plan's line references 361, 388 and ticket_links:203 are note writers, not ticket writers.
- The uuid and `rmm_client_id` model columns are `Mapped[str]`. `app/audit.py` is outside my list and cannot serialise `UUID` objects, so str values keep audit snapshots JSON-safe. The API output still emits UUIDs.
- The automation SOURCES tuple is exactly the plan's six values. `project` is not selectable in rules.
- Asset `external_id` is not populated by sync. It is reserved for the RMM, and the backfill leaves it null.

## Issues Encountered
- The one full-suite run (`pytest tests`) was polluted. I started the new test file while it was still running, and the two shared one test database, so it hit TRUNCATE deadlocks. It reported 9 failed and 28 errors, mostly in the calendar tests, and I did not re-run the whole suite. The 10 verification files above pass on their own.
- The order the plan lists the test files in did not match how I ran them, but all pass together.

## Escalations
| # | Severity | Type | Decision | Status | Resolution |
|---|----------|------|----------|--------|------------|
| 1 | warning | schema | Should `project` stay a valid ticket source? The owner-approved list is manual, email, portal, rmm, api, rule. | approved | Auto-run default: keep 'project' as a ticket source. It already exists and is used by app/projects.py. The owner's list was drawn up from a survey that missed it. Keeping it is additive and changes no behaviour. The owner is told in the run report. |

- #1 context: The CHECK and the `TicketSource` Literal currently include `project`, because `app/projects.py` sets it and the project tests and the `ck_tickets_source` check in test_projects_schema depend on it. Dropping it needs edits to `app/projects.py` and `tests/test_projects*.py`, which are outside this plan's file list. The alternative is to map project tickets to `manual`.

## Handoff Context
- **Key outputs**: backend/alembic/versions/0033_integration_readiness.py; backend/app/asset_schemas.py; backend/app/asset_sync.py; backend/app/assets.py; backend/app/auth/oidc.py; backend/app/automation.py; backend/app/models.py; backend/app/repositories.py; backend/app/routers/tickets.py; backend/app/schemas.py; backend/app/services.py; backend/app/ticket_services.py; backend/app/ticket_views.py; backend/tests/test_automation.py; backend/tests/test_events.py; backend/tests/test_integration_readiness.py; backend/tests/test_seed_and_migrations.py; backend/tests/test_tickets.py; backend/tests/test_webhooks.py; docs/INTEGRATIONS.md
- **Decisions made**: Kept `project` in the ticket source CHECK and in the `TicketSource` Literal. `app/projects.py` (not in my file list) creates tickets with source `project`, and the plan's six values would break it and its tests.; Note `source` (`ui`/`email`) is a separate column with its own CHECK, so I left it alone. The plan's line references 361, 388 and ticket_links:203 are note writers, not ticket writers.; The uuid and `rmm_client_id` model columns are `Mapped[str]`. `app/audit.py` is outside my list and cannot serialise `UUID` objects, so str values keep audit snapshots JSON-safe. The API output still emits UUIDs.; The automation SOURCES tuple is exactly the plan's six values. `project` is not selectable in rules.; Asset `external_id` is not populated by sync. It is reserved for the RMM, and the backfill leaves it null.
- **Open questions**: (none)
- **Conventions established**: Ticket source values are `manual`, `email`, `portal`, `rmm`, `api`, `rule` and `project`. Anything still sending `ui` fails the CHECK.; Time entries for automation use `entry_type='automation'`, and billing already skips them because `billable` is false.; Run the full backend suite once, alone, before wave 2, to confirm the calendar failures were only the deadlock.

## Requirements Covered
- REQ-14

## Token Usage
54 requests, 3774103 input tokens (3574114 cached), 31974 output tokens, $1.5345
