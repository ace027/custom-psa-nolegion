# Plan 08-01 Summary: Projects schema, permissions and approved money rules

## Result
**Status**: Complete
**Wave**: 1
**Agent**: engineering-backend-architect
**Completed**: 2026-10-21

## Agent Selection Rationale

| Candidate | Semantic | Heuristic | Memory | Total | Source |
|-----------|----------|-----------|--------|-------|--------|
| engineering-backend-architect | — | 18 | 3.25 | 21.25 | mandatory |
| engineering-senior-developer | — | 19 | 3.08 | 22.08 | heuristic |
| testing-qa-verification-specialist | — | 13 | 3.73 | 16.73 | heuristic |

- **Task type detected**: implementation
- **Confidence**: LOW
- **Adapter**: claude-code
- **Model tier**: sonnet

## Completed Tasks
- [x] Task 1: Migration 0029 and models (done)
- [x] Task 2: Permission and schema tests (done)
- [x] Task 3: Money rules in BILLING.md (done)

## Files Modified
- `backend/alembic/versions/0029_projects.py`
- `backend/app/models.py`
- `backend/app/permissions.py`
- `backend/tests/conftest.py`
- `backend/tests/test_permissions.py`
- `backend/tests/test_projects_schema.py`
- `docs/BILLING.md`

## Verification Results
6/6 verification commands passed (run by Triad after the agent finished).

## Verification Commands
| Command | Exit Code | Result |
|---------|-----------|--------|
| `service postgresql start >/dev/null 2>&1; cd backend && ruff check app tests && ruff format --check app tests` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_projects_schema.py tests/test_permissions.py tests/test_invoicing.py tests/test_tickets.py tests/test_automation_schema.py` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && alembic upgrade head && alembic downgrade 0028 && alembic upgrade head` | 0 | PASS |
| `cd backend && grep -q 'project_task_dependencies, project_tasks, project_phases, projects' tests/conftest.py` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_projects_schema.py tests/test_permissions.py` | 0 | PASS |
| `grep -q '## Project billing' docs/BILLING.md && grep -q 'capped at the project budget' docs/BILLING.md` | 0 | PASS |

## Key Decisions
- `uq_tickets_id_org` already exists (from 0024), so I did not add it again.
- The downgrade sets `tickets.source` 'project' to 'ui' and deletes `invoice_lines` with kind 'project', mirroring 0020.
- The `fixed_fee_invoice_line_id` and `owner_id` FKs are plain FKs, as the plan specifies.
- The project phase and dependency uniques (`uq_project_phases_id_org`, `uq_project_tasks_id_org`) support the composite FKs.

## Issues Encountered
(none)

## Escalations
(none)

## Handoff Context
- **Key outputs**: backend/alembic/versions/0029_projects.py; backend/app/models.py; backend/app/permissions.py; backend/tests/conftest.py; backend/tests/test_permissions.py; backend/tests/test_projects_schema.py; docs/BILLING.md
- **Decisions made**: `uq_tickets_id_org` already exists (from 0024), so I did not add it again.; The downgrade sets `tickets.source` 'project' to 'ui' and deletes `invoice_lines` with kind 'project', mirroring 0020.; The `fixed_fee_invoice_line_id` and `owner_id` FKs are plain FKs, as the plan specifies.; The project phase and dependency uniques (`uq_project_phases_id_org`, `uq_project_tasks_id_org`) support the composite FKs.
- **Open questions**: (none)
- **Conventions established**: `ProjectTask.ticket` is a joined viewonly relationship, and `Project`, `ProjectPhase` and `ProjectTask` carry no ORM FK to the composite targets. Plan 08-02 should set `organization_id` explicitly on inserts and rely on the database FKs.; Constraint names to match on: `ck_projects_*`, `fk_project_tasks_{project,phase,ticket}_org`, `fk_project_task_deps_{task,dep}_org`, `uq_project_tasks_ticket`, `uq_project_task_deps`, `fk_tickets_project_org`.; The app role has DELETE only on `project_phases` and `project_task_dependencies`.; 08-02 route tests must hit `project:write` endpoints for the `test_zz_api_contract` check.; `.planning/STATE.md` and `.planning/memory/PREFERENCES.md` show as modified in git status. I did not touch them.

## Requirements Covered
- REQ-08

## Token Usage
11 requests, 445768 input tokens (391537 cached), 16396 output tokens, $0.3778
