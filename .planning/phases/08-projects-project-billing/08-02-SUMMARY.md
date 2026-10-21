# Plan 08-02 Summary: Projects, phases, tasks, dependencies and budget vs actual API

## Result
**Status**: Complete
**Wave**: 2
**Agent**: engineering-senior-developer
**Completed**: 2026-10-21

## Agent Selection Rationale

| Candidate | Semantic | Heuristic | Memory | Total | Source |
|-----------|----------|-----------|--------|-------|--------|
| engineering-senior-developer | — | 23 | 3.08 | 26.08 | heuristic |
| engineering-backend-architect | — | 17 | 3.25 | 20.25 | heuristic |
| testing-qa-verification-specialist | — | 13 | 3.73 | 16.73 | heuristic |

- **Task type detected**: implementation
- **Confidence**: HIGH
- **Adapter**: claude-code
- **Model tier**: sonnet

## Completed Tasks
- [x] Task 1: Project service (done)
- [x] Task 2: Routes and tests (done)

## Files Modified
- `backend/app/main.py`
- `backend/app/project_schemas.py`
- `backend/app/projects.py`
- `backend/app/routers/projects.py`
- `backend/app/schemas.py`
- `backend/app/ticket_views.py`
- `backend/tests/test_projects.py`
- `backend/tests/test_projects_api.py`

## Verification Results
4/4 verification commands passed (run by Triad after the agent finished).

## Verification Commands
| Command | Exit Code | Result |
|---------|-----------|--------|
| `service postgresql start >/dev/null 2>&1; cd backend && ruff check app tests && ruff format --check app tests` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_projects.py tests/test_projects_api.py tests/test_projects_schema.py tests/test_tickets.py tests/test_portal.py` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -c 'import app.projects'` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_projects.py tests/test_projects_api.py tests/test_tickets.py` | 0 | PASS |

## Key Decisions
- `attach_ticket` only sets `tickets.project_id` and creates no task row, because the app role has no DELETE on `project_tasks` and detach could not remove one. A task's own ticket is the one that has a `project_tasks` row, and detaching it returns 409.
- `actual_minutes` and `billable_minutes` are both the sum of `minutes_billable` over non-voided entries, as the plan literally says, so they are always equal. Raw `minutes_actual` is not exposed.
- `over_budget` is true when cost at rates exceeds the cap: `budget_cents` for T&M, `fixed_fee_cents` for fixed fee. `remaining_cents` is null for fixed fee and for a T&M draft with no budget.
- `set_status` rejects draft to active (use approve) and any same-status change. `on_hold` can only go back to `active`. Completed and cancelled projects take no new phases, tasks or attached tickets (409).
- `can_bill` checks `billing:write` on the user's role. For API-key requests it uses `api_keys.effective_permission`, so a key without that scope cannot set billing fields.
- Dependency routes take the `project_id` from the URL and pass it through; a task that belongs to another project returns 404.
- `add_task` leaves the new ticket in `new` status even when an assignee is set, matching `create_ticket`.

## Issues Encountered
- `.planning/memory/PREFERENCES.md` shows as modified in git status; I did not touch it.
- `TaskPatch` accepts `status` and `status_id` and routes them through `ticket_services.update_ticket`, so dependencies never block status changes, as the context says.

## Escalations
(none)

## Handoff Context
- **Key outputs**: backend/app/main.py; backend/app/project_schemas.py; backend/app/projects.py; backend/app/routers/projects.py; backend/app/schemas.py; backend/app/ticket_views.py; backend/tests/test_projects.py; backend/tests/test_projects_api.py
- **Decisions made**: `attach_ticket` only sets `tickets.project_id` and creates no task row, because the app role has no DELETE on `project_tasks` and detach could not remove one. A task's own ticket is the one that has a `project_tasks` row, and detaching it returns 409.; `actual_minutes` and `billable_minutes` are both the sum of `minutes_billable` over non-voided entries, as the plan literally says, so they are always equal. Raw `minutes_actual` is not exposed.; `over_budget` is true when cost at rates exceeds the cap: `budget_cents` for T&M, `fixed_fee_cents` for fixed fee. `remaining_cents` is null for fixed fee and for a T&M draft with no budget.; `set_status` rejects draft to active (use approve) and any same-status change. `on_hold` can only go back to `active`. Completed and cancelled projects take no new phases, tasks or attached tickets (409).; `can_bill` checks `billing:write` on the user's role. For API-key requests it uses `api_keys.effective_permission`, so a key without that scope cannot set billing fields.; Dependency routes take the `project_id` from the URL and pass it through; a task that belongs to another project returns 404.; `add_task` leaves the new ticket in `new` status even when an assignee is set, matching `create_ticket`.
- **Open questions**: (none)
- **Conventions established**: `projects.detail(ctx, project)`, `summary`, `task_rows` and `phase_rows` return the dicts that build `ProjectOut`, `ProjectSummaryOut`, `TaskOut` and `PhaseOut`. Plan 08-03 can reuse `projects.budget(ctx, id)` for billed totals.; Billing in 08-03 should count a project's time via `tickets.project_id`. This covers both task tickets and attached tickets.; `budget()` reads `InvoiceLine.project_id` with `voided = false` on invoices whose status is not `void`. The 08-03 lines must set `project_id` to match.; The routes `POST /api/projects/{id}/bill-fixed-fee` and `fixed_fee_billed` are not part of this plan. `fixed_fee_billed` is already exposed as `fixed_fee_invoice_line_id is not None`.

## Requirements Covered
- REQ-08

## Token Usage
30 requests, 2152641 input tokens (2052808 cached), 45160 output tokens, $1.1117
