# Plan 05-01 Summary: Schema, models, schemas and on-call math

## Result
**Status**: Partial
**Wave**: 1
**Agent**: engineering-backend-architect
**Completed**: 2026-10-15

## Agent Selection Rationale

| Candidate | Semantic | Heuristic | Memory | Total | Source |
|-----------|----------|-----------|--------|-------|--------|
| engineering-backend-architect | — | 18 | 3.72 | 21.72 | mandatory |
| engineering-senior-developer | — | 19 | 3.78 | 22.78 | heuristic |
| testing-qa-verification-specialist | — | 12 | 4.38 | 16.38 | heuristic |

- **Task type detected**: implementation
- **Confidence**: LOW
- **Adapter**: claude-code
- **Model tier**: sonnet

## Completed Tasks
- [x] Task 1: Migration 0026 and models (done)
- [x] Task 2: Schemas (done)
- [x] Task 3: Pure on-call math and tests (done)

## Files Modified
- `backend/alembic/versions/0026_client_notices_oncall.py`
- `backend/app/models.py`
- `backend/app/oncall.py`
- `backend/app/oncall_schemas.py`
- `backend/app/scheduling_schemas.py`
- `backend/app/schemas.py`
- `backend/tests/test_client_notices_oncall_schema.py`
- `backend/tests/test_oncall_math.py`

## Verification Results
5/5 verification commands passed (run by Triad after the agent finished).

## Verification Commands
| Command | Exit Code | Result |
|---------|-----------|--------|
| `service postgresql start >/dev/null 2>&1; cd backend && ruff check app tests && ruff format --check app tests` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m alembic upgrade head && python -m alembic downgrade 0025 && python -m alembic upgrade head` | 0 | PASS |
| `cd backend && python -c 'import app.oncall_schemas, app.scheduling_schemas, app.schemas'` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_oncall_math.py tests/test_client_notices_oncall_schema.py` | 0 | PASS |

## Key Decisions
- `AppointmentOut.notify_client` defaults to True instead of being required. The existing `routers/scheduling.py` builds `AppointmentOut` without that field, so a required field returned a 500 on the appointment create endpoint. Plan 05-02 should populate it and may then make it required.
- IDs are `BigInteger` Identity, matching the existing tables, rather than serial.
- The notice pending-unique index is named `uq_appointment_notices_pending`. Constraint names are `ck_appointment_notices_state`, `ck_appointment_notices_kind`, `ck_oncall_rotations_weekday`, `ck_oncall_rotations_anchor`, `ck_oncall_overrides_range`, `uq_oncall_members_position` and `uq_oncall_members_user`.
- In `who_is_on`, `until` for a rotation shift is the earlier of the next handoff and the next override start. For an override it is the earlier of the override's end and the next override start.
- A handoff time that falls in a DST gap resolves through zoneinfo's fold=0 behaviour. A test pins this.

## Issues Encountered
- The full-suite result is unconfirmed. Re-run `cd backend && python -m pytest -q` with nothing else using the test DB. The suite takes about 3.5 minutes or more.

## Escalations
(none)

## Handoff Context
- **Key outputs**: backend/alembic/versions/0026_client_notices_oncall.py; backend/app/models.py; backend/app/oncall.py; backend/app/oncall_schemas.py; backend/app/scheduling_schemas.py; backend/app/schemas.py; backend/tests/test_client_notices_oncall_schema.py; backend/tests/test_oncall_math.py
- **Decisions made**: `AppointmentOut.notify_client` defaults to True instead of being required. The existing `routers/scheduling.py` builds `AppointmentOut` without that field, so a required field returned a 500 on the appointment create endpoint. Plan 05-02 should populate it and may then make it required.; IDs are `BigInteger` Identity, matching the existing tables, rather than serial.; The notice pending-unique index is named `uq_appointment_notices_pending`. Constraint names are `ck_appointment_notices_state`, `ck_appointment_notices_kind`, `ck_oncall_rotations_weekday`, `ck_oncall_rotations_anchor`, `ck_oncall_overrides_range`, `uq_oncall_members_position` and `uq_oncall_members_user`.; In `who_is_on`, `until` for a rotation shift is the earlier of the next handoff and the next override start. For an override it is the earlier of the override's end and the next override start.; A handoff time that falls in a DST gap resolves through zoneinfo's fold=0 behaviour. A test pins this.
- **Open questions**: (none)
- **Conventions established**: `app.oncall.who_is_on(rotation, members, overrides, at, tz)` and `shifts(...)` take duck-typed ORM objects: rotation needs `handoff_weekday`, `handoff_time`, `anchor_date` and `active`; members need `user_id` and `position`; overrides need `user_id`, `starts_at`, `ends_at` and `created_at`.; `shifts` returns `Shift(user_id, starts_at, ends_at, source)` with UTC datetimes and leaves out time when nobody is on call.; The router work in the next plan must set `notify_client` and `client_notice` on `AppointmentOut`.

## Requirements Covered
- REQ-05

## Token Usage
20 requests, 1010298 input tokens (780684 cached), 24264 output tokens, $0.9728
