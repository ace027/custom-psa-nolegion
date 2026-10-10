# Plan 02-01 Summary: Scheduling schema, RLS and permissions

## Result
**Status**: Complete
**Wave**: 1
**Agent**: engineering-backend-architect
**Completed**: 2026-10-09

## Agent Selection Rationale

| Candidate | Semantic | Heuristic | Memory | Total | Source |
|-----------|----------|-----------|--------|-------|--------|
| engineering-backend-architect | — | 15 | 0 | 15 | mandatory |
| engineering-senior-developer | — | 19 | 4.75 | 23.75 | heuristic |
| testing-api-tester | — | 15 | 0 | 15 | heuristic |

- **Task type detected**: implementation
- **Confidence**: LOW
- **Adapter**: claude-code
- **Model tier**: sonnet

## Completed Tasks
- [x] Task 1: Migration 0024_scheduling (done)
- [x] Task 2: Models and permissions (done)
- [x] Task 3: Schema tests (done)

## Files Modified
- `backend/alembic/versions/0024_scheduling.py`
- `backend/app/models.py`
- `backend/app/permissions.py`
- `backend/tests/test_scheduling_schema.py`

## Verification Results
5/5 verification commands passed (run by Triad after the agent finished).

## Verification Commands
| Command | Exit Code | Result |
|---------|-----------|--------|
| `cd backend && python -m pytest -q tests/test_scheduling_schema.py tests/test_isolation.py tests/test_seed_and_migrations.py` | 0 | PASS |
| `cd backend && ruff check app tests && ruff format --check app tests` | 0 | PASS |
| `cd backend && python -m pytest -q tests/test_seed_and_migrations.py` | 0 | PASS |
| `cd backend && python -c "from app import permissions as P; assert P.has_permission('read_only','schedule:read') and P.has_permission('billing','schedule:read'); assert P.has_permission('tech','schedule:write') and not P.has_permission('billing','schedule:write'); assert P.has_permission('admin','timeoff:approve') and not P.has_permission('tech','timeoff:approve')"` | 0 | PASS |
| `cd backend && python -m pytest -q tests/test_scheduling_schema.py tests/test_isolation.py` | 0 | PASS |

## Key Decisions
- Appointment has no ticket or tech relationship(), only plain FK columns. Its organization_id is shared by two FKs (fk_appointments_org and the composite ticket FK), so a relationship would trigger SQLAlchemy overlap warnings; routers can join explicitly.

## Issues Encountered
- none. backend/app/availability.py and backend/tests/test_availability.py are new, untracked files that I did not create; they appear to belong to the parallel plan 02-02, and I left them alone.

## Escalations
(none)

## Handoff Context
- **Key outputs**: backend/alembic/versions/0024_scheduling.py; backend/app/models.py; backend/app/permissions.py; backend/tests/test_scheduling_schema.py
- **Decisions made**: Appointment has no ticket or tech relationship(), only plain FK columns. Its organization_id is shared by two FKs (fk_appointments_org and the composite ticket FK), so a relationship would trigger SQLAlchemy overlap warnings; routers can join explicitly.
- **Open questions**: (none)
- **Conventions established**: The app role (psa_app) has SELECT/INSERT/UPDATE/DELETE on user_work_hours (no RLS), SELECT/INSERT/UPDATE on user_time_off (no RLS, no delete) and SELECT/INSERT/UPDATE on appointments (forced RLS, no delete). To cancel, set status='cancelled' and cancelled_at together; ck_appointments_cancelled requires both.

## Requirements Covered
- REQ-02

## Token Usage
18 requests, 705099 input tokens (649215 cached), 15685 output tokens, $0.7229
