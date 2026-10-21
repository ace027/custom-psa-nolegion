---
phase: 08-projects-project-billing
compacted: 2026-10-21
original_summaries: [08-01-SUMMARY.md, 08-02-SUMMARY.md, 08-03-SUMMARY.md, 08-04-SUMMARY.md]
requirements_satisfied: [REQ-08]
---

# Phase 8: Projects & project billing — Compacted Summary

## Deliverables
- 08-01 Projects schema, permissions and approved money rules (Complete): backend/alembic/versions/0029_projects.py, backend/app/models.py, backend/app/permissions.py, backend/tests/conftest.py, backend/tests/test_permissions.py, backend/tests/test_projects_schema.py, docs/BILLING.md
- 08-02 Projects, phases, tasks, dependencies and budget vs actual API (Complete): backend/app/main.py, backend/app/project_schemas.py, backend/app/projects.py, backend/app/routers/projects.py, backend/app/schemas.py, backend/app/ticket_views.py, backend/tests/test_projects.py, backend/tests/test_projects_api.py
- 08-03 Project billing: fixed fee up front and capped T&M (Complete with Warnings): backend/app/reports.py, backend/app/schemas.py
- 08-04 Projects UI: list, detail, board view, budget card, seed and verify checklist (Complete): backend/tests/test_seed_and_migrations.py

## Decisions
- 08-01: `uq_tickets_id_org` already exists (from 0024), so I did not add it again.
- 08-01: The downgrade sets `tickets.source` 'project' to 'ui' and deletes `invoice_lines` with kind 'project', mirroring 0020.
- 08-01: The `fixed_fee_invoice_line_id` and `owner_id` FKs are plain FKs, as the plan specifies.
- 08-02: `attach_ticket` only sets `tickets.project_id` and creates no task row, because the app role has no DELETE on `project_tasks` and detach could not remove one. A
- 08-02: `actual_minutes` and `billable_minutes` are both the sum of `minutes_billable` over non-voided entries, as the plan literally says, so they are always equal. Ra
- 08-02: `over_budget` is true when cost at rates exceeds the cap: `budget_cents` for T&M, `fixed_fee_cents` for fixed fee. `remaining_cents` is null for fixed fee and f
- 08-03: T&M groups are sorted by (ticket number, work type id). A group whose work type has no rate is left unbilled with the existing warning, whether or not the budge
- 08-04: Besides the tickets count, two more seed-test assertions also depended on the ticket total: dashboard open (5 to 12) and my_open (2 to 6). I updated both as con

## Conventions and Open Questions
- 08-01 convention: `ProjectTask.ticket` is a joined viewonly relationship, and `Project`, `ProjectPhase` and `ProjectTask` carry no ORM FK to the composite targets. Plan 08-02 sho
- 08-01 convention: Constraint names to match on: `ck_projects_*`, `fk_project_tasks_{project,phase,ticket}_org`, `fk_project_task_deps_{task,dep}_org`, `uq_project_tasks_ticket`, 
- 08-01 convention: The app role has DELETE only on `project_phases` and `project_task_dependencies`.
- 08-02 convention: `projects.detail(ctx, project)`, `summary`, `task_rows` and `phase_rows` return the dicts that build `ProjectOut`, `ProjectSummaryOut`, `TaskOut` and `PhaseOut`
- 08-02 convention: Billing in 08-03 should count a project's time via `tickets.project_id`. This covers both task tickets and attached tickets.
- 08-02 convention: `budget()` reads `InvoiceLine.project_id` with `voided = false` on invoices whose status is not `void`. The 08-03 lines must set `project_id` to match.
- 08-03 convention: The bill-fixed-fee route returns InvoiceOut with status 201. Errors are 409 "The fixed fee is already billed", 409 "Approve the project before billing its fee" 
- 08-04 convention: Seed now creates 12 tickets in total, 7 of them project task tickets. Later tests that count seeded tickets must expect 12.

## Files Modified
| File | Change |
|------|--------|
| `backend/alembic/versions/0029_projects.py` | 08-01: Projects schema, permissions and approved money rules |
| `backend/app/models.py` | 08-01: Projects schema, permissions and approved money rules |
| `backend/app/permissions.py` | 08-01: Projects schema, permissions and approved money rules |
| `backend/tests/conftest.py` | 08-01: Projects schema, permissions and approved money rules |
| `backend/tests/test_permissions.py` | 08-01: Projects schema, permissions and approved money rules |
| `backend/tests/test_projects_schema.py` | 08-01: Projects schema, permissions and approved money rules |
| `docs/BILLING.md` | 08-01: Projects schema, permissions and approved money rules |
| `backend/app/main.py` | 08-02: Projects, phases, tasks, dependencies and budget vs actual API |
| `backend/app/project_schemas.py` | 08-02: Projects, phases, tasks, dependencies and budget vs actual API |
| `backend/app/projects.py` | 08-02: Projects, phases, tasks, dependencies and budget vs actual API |
| `backend/app/routers/projects.py` | 08-02: Projects, phases, tasks, dependencies and budget vs actual API |
| `backend/app/schemas.py` | 08-02: Projects, phases, tasks, dependencies and budget vs actual API |
| `backend/app/ticket_views.py` | 08-02: Projects, phases, tasks, dependencies and budget vs actual API |
| `backend/tests/test_projects.py` | 08-02: Projects, phases, tasks, dependencies and budget vs actual API |
| `backend/tests/test_projects_api.py` | 08-02: Projects, phases, tasks, dependencies and budget vs actual API |
| `backend/app/reports.py` | 08-03: Project billing: fixed fee up front and capped T&M |
| `backend/app/schemas.py` | 08-03: Project billing: fixed fee up front and capped T&M |
| `backend/tests/test_seed_and_migrations.py` | 08-04: Projects UI: list, detail, board view, budget card, seed and verify checklist |

## Verification
- 08-01 (REQ-08): 6/6 verification commands passed
- 08-02 (REQ-08): 4/4 verification commands passed
- 08-03 (REQ-08): 6/6 verification commands passed
- 08-04 (REQ-08): 6/6 verification commands passed

## Agents
- 08-01: engineering-backend-architect
- 08-02: engineering-senior-developer
- 08-03: engineering-senior-developer
- 08-04: engineering-frontend-developer

## Also Covered
- backend/app/ticket_services.py
- backend/app/billing.py
- backend/app/billing_repo.py
- backend/tests/test_project_billing.py
- frontend/src/api.ts
- frontend/src/App.tsx
- frontend/src/pages/Projects.tsx
- frontend/src/pages/ProjectDetail.tsx
- frontend/src/pages/ProjectBoard.tsx
- frontend/src/pages/OrgProjectsCard.tsx
- frontend/src/pages/OrganizationDetail.tsx
- frontend/src/pages/TicketDetail.tsx
- frontend/src/Projects.test.tsx
- backend/app/seed.py
- docs/verify/projects.md
- .planning/VERIFY.md
