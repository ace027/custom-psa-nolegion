# Phase 2: Scheduling: availability & appointments — Review Summary

## Result: PASSED

**Cycles Used**: 1
**Reviewers**: testing-qa-verification-specialist, engineering-backend-architect, engineering-frontend-developer
**Evaluators**: code-quality, integration, business-logic
**Completed**: 2026-10-09

## Findings Summary
- Must-fix (blocker, critical, major) found: 0; fixed: 0; unresolved: 0
- Suggestions (minor, advisory): 2
- Deferred (confidence 50-79%): 16
- Hot spots (flagged by 2+ reviewers): `backend/app/scheduling.py`, `backend/app/routers/scheduling.py`, `backend/tests/test_scheduling_api.py`, `backend/tests/test_availability.py`

## Findings Detail
| ID | Severity | Location | Issue | Reviewers | Confidence | Status |
|----|----------|----------|-------|-----------|------------|--------|
| F-001 | minor | `backend/app/scheduling.py:135-151` | `_schedule_view` rebuilds the weekly map inline (default-hours fallback included). `_weekly` (87-91) already does this, so the logic exists twice. | evaluator:code-quality | 85% | deferred |
| F-002 | advisory | `backend/app/scheduling.py:44` | mypy reports `union-attr` errors where `ctx.user` (`User / None`) is dereferenced. Line 521 also passes `tech` (`User / None`) to `_working`, which expects `User`. The errors at lines 44-438 follow the existing pattern (63 such errors across `app`); line 521 is specific to this change. | evaluator:code-quality | 80% | deferred |

## Reviewer Verdicts
- Cycle 1, testing-qa-verification-specialist: **NEEDS WORK**
- Cycle 1, engineering-backend-architect: **NEEDS WORK**
- Cycle 1, engineering-frontend-developer: **PASS**
- Cycle 1, evaluator:code-quality: **NEEDS WORK**
- Cycle 1, evaluator:integration: **PASS**
- Cycle 1, evaluator:business-logic: **NEEDS WORK**

## Suggestions (Not Required)
- F-001 `backend/app/scheduling.py`: `_schedule_view` rebuilds the weekly map inline (default-hours fallback included). `_weekly` (87-91) already does this, so the logic exists twice. (fix: Call `_weekly(ctx, user)` in `_schedule_view`. Keep `rows` for `uses_default_hours`, or return that flag from a small shared helper.)
- F-002 `backend/app/scheduling.py`: mypy reports `union-attr` errors where `ctx.user` (`User | None`) is dereferenced. Line 521 also passes `tech` (`User | None`) to `_working`, which expects `User`. The errors at lines 44-438 follow the existing pattern (63 such errors across `app`); line 521 is specific to this change. (fix: Add a `ctx.require_user()` helper (or an assert) and use it in these functions. In `conflicts_for`, raise `NotFound` if `tech is None`. Type-safety category (evaluator:code-quality:pass:2).)

## Deferred (Medium Confidence)
- `backend/app/scheduling.py` [major, 70%]: `decide_time_off` and `cancel_time_off` read the row with a plain `ctx.db.get` and check `status` in Python. They take no row lock and use no compare-and-set on the status.
- `backend/app/scheduling.py` [minor, 60%]: `update_appointment` sets `a.tech_id` (line 408) before `_range` validates the new times (line 411). It also uses `data.get("starts_at") or a.starts_at`, so an explicit `starts_at: null` or `ends_at: null` in the PATCH is silently ignored instead of rejected. The schema allows `None`.
- `backend/app/routers/scheduling.py` [minor, 60%]: `user_ids` has no limit on how many ids it takes. It only has a `max_length` of 2000 characters, which allows about 1000 ids. Each id runs about 5 queries in `availability_for`, over a range of up to 31 days. `list_time_off` also calls `time_off_view` per row, and each call does a user lookup, over up to 1000 rows.
- `backend/app/scheduling.py` [minor, 60%]: `data.get("user_id") or ctx.user.id` treats `user_id=0` as "self".
- `backend/app/scheduling.py` [minor, 50%]: `conflicts_for` calls `repo.get_user` and passes the result straight to `_working` without a `None` check.
- `backend/alembic/versions/0024_scheduling.py` [major, 60%]: The composite FK `(ticket_id, organization_id)` uses `ON UPDATE CASCADE`, and `appointments.organization_id` is NOT NULL. `scheduling.py:370` shows tickets can have a NULL `organization_id`. If a ticket with appointments is set back to no client, the cascade tries to set `appointments.organization_id` to NULL and fails with a NOT NULL violation. The result is probably a 500 on the ticket update. Nothing in the migration, the service or the tests covers this case.
- `backend/app/scheduling.py` [minor, 65%]: `list_time_off` and `list_appointments` truncate silently at 1000 and 2000 rows. The API has no pagination, no total count and no truncation signal. `list_time_off` accepts no range at all.
- `backend/app/scheduling.py` [minor, 70%]: `_bookable` raises `Conflict` (409) when the user does not exist. A nonexistent `user_ids` entry on `GET /availability`, or a `user_id` on `PUT /users/{id}/schedule`, returns 409 instead of 404. `GET /users/{id}/schedule` already returns 404 for the same case.
- `backend/app/scheduling.py` [minor, 65%]: `availability_for` runs a loop per user. Each iteration runs about 6 queries: settings, work hours, holidays, time off, appointments, and `get_user` for the tech. The default call covers every active tech and has no cap on `user_ids`. The 31-day range is allowed for all of them.
- `backend/app/routers/scheduling.py` [minor, 50%]: `GET /time-off` is gated only by `SCHEDULE_READ`, which `read_only` and `billing` roles hold. Any such role can list every tech's time-off windows, status and names across the whole org. Only the reason is hidden.
- `backend/app/scheduling.py` [minor, 55%]: `_tz` calls `ZoneInfo(user.timezone or settings.timezone)` with no error handling. `_zone` handles the error, but only at write time.
- `backend/app/scheduling.py` [advisory, 60%]: `put_schedule` re-checks the empty list, duplicate weekdays and minute ordering, which `SchedulePut` and `WorkHoursDay` already enforce. Through the API these `InvalidSchedule` branches cannot be reached, so tests never exercise them. `_human` is also only reached through `_range`.
- `backend/app/scheduling.py` [advisory, 50%]: Date padding is applied three times. `_local_dates` pads one day for the holiday lookup. `working_windows` pads one day again. `conflicts_for` also widens the range by one day each side before calling `_working`.
- `backend/app/scheduling.py` [minor, 70%]: `time_off_view` and `appointment_view` do 1 to 3 lookups per row (`get_user`, `Organization`, `Ticket`). The list endpoints return up to 1000 time-off rows and 2000 appointments.
- `backend/tests/test_scheduling_api.py` [minor, 55%]: No API-level test covers: - an appointment tied to a ticket in another organization, or a scoped caller reading another organization's appointment (the isolation check exists only in `test_scheduling_schema.py` at the DB level); - PATCH with `starts_at: null`; - a non-numeric or invalid stored timezone at read time; - `PUT` of a timezone for an inactive or non-bookable user.
- `backend/tests/test_availability.py` [major, 75%]: The criterion asks for DST property tests. The only randomized test, `test_subtract_property`, covers interval subtraction and never touches time zones. The DST coverage is fixed examples: one 2026 sweep over `ZONES`, six parametrized DST days, and one spring-forward gap case. Nothing randomizes `working_windows` over zone, weekly map, holidays and range. Nothing checks the 1440 ("next local midnight") path on DST days with a nonzero start. Nothing covers the fall-back ambiguous hour (01:30 on 2026-11-01 in Chicago). Nothing covers southern-hemisphere or half-hour-offset zones with DST, such as Australia/Lord_Howe or America/St_Johns. Hypothesis is not installed.

## Coverage
No coverage data found (looked for coverage/coverage-summary.json, coverage-summary.json, coverage/lcov.info, lcov.info, coverage.xml, coverage/cobertura-coverage.xml, coverage/coverage.xml, coverage.txt, coverage/coverage.txt). Advisory only: run the test suite with coverage to check review.coverage_thresholds.
