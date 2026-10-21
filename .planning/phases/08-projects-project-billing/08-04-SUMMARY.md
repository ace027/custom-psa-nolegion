# Plan 08-04 Summary: Projects UI: list, detail, board view, budget card, seed and verify checklist

## Result
**Status**: Partial
**Wave**: 3
**Agent**: engineering-frontend-developer
**Completed**: 2026-10-21
**Failure Class**: BLOCKER — $ service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_seed_and_migrations.py (exit 1)

## Agent Selection Rationale

| Candidate | Semantic | Heuristic | Memory | Total | Source |
|-----------|----------|-----------|--------|-------|--------|
| engineering-frontend-developer | — | 13 | 3.42 | 16.42 | mandatory |
| engineering-senior-developer | — | 23 | 3.08 | 26.08 | heuristic |
| engineering-backend-architect | — | 14 | 3.25 | 17.25 | heuristic |

- **Task type detected**: implementation
- **Confidence**: LOW
- **Adapter**: claude-code
- **Model tier**: sonnet

## Completed Tasks
- [x] Task 1: API client and pages (done)
- [x] Task 2: Org card, ticket link and tests (done)
- [ ] Task 3: Seed and verify checklist (partial)

## Files Modified
- `backend/app/seed.py`
- `docs/verify/projects.md`
- `frontend/src/App.tsx`
- `frontend/src/Projects.test.tsx`
- `frontend/src/api.ts`
- `frontend/src/pages/OrgProjectsCard.tsx`
- `frontend/src/pages/OrganizationDetail.tsx`
- `frontend/src/pages/ProjectBoard.tsx`
- `frontend/src/pages/ProjectDetail.tsx`
- `frontend/src/pages/Projects.tsx`
- `frontend/src/pages/TicketDetail.tsx`

## Verification Results
5/6 verification commands passed (run by Triad after the agent finished).

## Verification Commands
| Command | Exit Code | Result |
|---------|-----------|--------|
| `service postgresql start >/dev/null 2>&1; cd backend && ruff check app tests && ruff format --check app tests` | 0 | PASS |
| `cd frontend && npm run typecheck && npx vitest run && npm run build` | 0 | PASS |
| `cd frontend && npm run typecheck` | 0 | PASS |
| `cd frontend && npm run typecheck && npx vitest run src/Projects.test.tsx` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_seed_and_migrations.py` | 1 | FAIL |
| `grep -q 'Phase 8' .planning/VERIFY.md && test -f docs/verify/projects.md` | 0 | PASS |

## Key Decisions
- Board moves PATCH `{status_id}`, using the first non-archived status with the target behavior from /ticket-statuses. The Resolved column also holds closed tasks.
- Dependencies are a checkbox group ("Depends on") instead of a multi-select element, for accessibility and easier testing. Edit saves add or remove dependency calls after the task PATCH.
- The list gets actual hours and remaining per row from /projects/{id}/budget, because ProjectSummaryOut has no budget fields.
- The seed uses Contoso Dental for the fixed fee and Fabrikam Engineering for the T&M project, both non-taxable.
- Write controls are hidden for users without project:write and for completed or cancelled projects.

## Issues Encountered
- tests/test_seed_and_migrations.py is not in my file list. After my change it needs tickets == 12, dashboard counts["open"] == 12 and len(my_open) == 6. I checked this with a temporary copy of the test, since deleted.
- The seed test also failed once before my seed change, with 4 organizations. That was probably the parallel 08-03 run sharing the test database, and it did not recur.
- I ran `git stash` and `git stash pop` once to compare against the baseline, which briefly touched the shared working tree. The pop succeeded and git status looked normal afterwards.
- bill-fixed-fee is called by the UI, but the route comes from 08-03 and is mocked in my tests.
- BLOCKER: $ service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_seed_and_migrations.py (exit 1)

## Escalations
| # | Severity | Type | Decision | Status | Resolution |
|---|----------|------|----------|--------|------------|
| 1 | warning | out-of-scope-file | Allow a change to backend/tests/test_seed_and_migrations.py, or tell me to drop the seed projects. | pending | INVALID: type "out-of-scope-file" is not one of architecture, dependency, scope, schema, api, deletion, infrastructure, quality |
| 2 | blocker | schema | Resolve: $ service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_seed_and_migrations.py (exit 1) | pending |  |

- #1 context: The plan requires seeded projects with tasks, and each task is a ticket. The existing seed test hard-codes the old counts, and the plan's verification command runs that test. The required edits are tickets 5 to 12, dashboard counts["open"] 5 to 12, and len(my_open) 2 to 6. The file is not in files_modified.
- #2 context: Verification failed (service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_seed_and_migrations.py); a BLOCKER is not auto-fixed.

## Handoff Context
- **Key outputs**: backend/app/seed.py; docs/verify/projects.md; frontend/src/App.tsx; frontend/src/Projects.test.tsx; frontend/src/api.ts; frontend/src/pages/OrgProjectsCard.tsx; frontend/src/pages/OrganizationDetail.tsx; frontend/src/pages/ProjectBoard.tsx; frontend/src/pages/ProjectDetail.tsx; frontend/src/pages/Projects.tsx; frontend/src/pages/TicketDetail.tsx
- **Decisions made**: Board moves PATCH `{status_id}`, using the first non-archived status with the target behavior from /ticket-statuses. The Resolved column also holds closed tasks.; Dependencies are a checkbox group ("Depends on") instead of a multi-select element, for accessibility and easier testing. Edit saves add or remove dependency calls after the task PATCH.; The list gets actual hours and remaining per row from /projects/{id}/budget, because ProjectSummaryOut has no budget fields.; The seed uses Contoso Dental for the fixed fee and Fabrikam Engineering for the T&M project, both non-taxable.; Write controls are hidden for users without project:write and for completed or cancelled projects.
- **Open questions**: (none)
- **Conventions established**: Query keys are ["project", id], ["project-budget", id] and ["projects", orgId, status].; Seed project time sits on task tickets, so it counts through tickets.project_id for the 08-03 billing runs.; Update test_seed_and_migrations.py to the counts above (tickets 12, open 12, my_open 6).

## Requirements Covered
- REQ-08

### Failed verification output
`service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_seed_and_migrations.py`
```
and the part of each time entry a billing run drew from a block
INFO     alembic.runtime.migration:migration.py:611 Running upgrade 0023 -> 0024, Scheduling: per-user timezone, working hours, time off, and client-owned appointments
INFO     alembic.runtime.migration:migration.py:611 Running upgrade 0024 -> 0025, Outlook push: the appointment_sync outbox, the busy cache and the outlook_sync_enabled setting
INFO     alembic.runtime.migration:migration.py:611 Running upgrade 0025 -> 0026, Client appointment notices and on-call rotations
INFO     alembic.runtime.migration:migration.py:611 Running upgrade 0026 -> 0027, RMM alerts to tickets: rmm_alerts, tickets.asset_id, ticket source 'rmm'
INFO     alembic.runtime.migration:migration.py:611 Running upgrade 0027 -> 0028, Automation and API: api_keys, webhook_endpoints, webhook_deliveries, automation_rules,
automation_runs, tickets.sla_breached_event_at, ticket source 'rule'
INFO     alembic.runtime.migration:migration.py:611 Running upgrade 0028 -> 0029, Projects: projects, project_phases, project_tasks, project_task_dependencies
----------------------------- Captured stdout call -----------------------------
Seeded 4 users, 3 organizations, demo tickets, billing, devices and projects.
Organizations already exist; skipping organizations and users.
=========================== short test summary info ============================
FAILED tests/test_seed_and_migrations.py::test_seed_is_idempotent_and_usable
1 failed, 2 passed in 6.56s

```

## Token Usage
27 requests, 1977904 input tokens (1882330 cached), 39009 output tokens, $1.0055
