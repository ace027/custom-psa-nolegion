---
phase: 05-client-confirmations-on-call
compacted: 2026-10-15
original_summaries: [05-01-SUMMARY.md, 05-02-SUMMARY.md, 05-03-SUMMARY.md, 05-04-SUMMARY.md, 05-05-SUMMARY.md]
requirements_satisfied: [REQ-05]
---

# Phase 5: Client confirmations + on-call — Compacted Summary

## Deliverables
- 05-01 Schema, models, schemas and on-call math (Complete)
- 05-02 Client appointment emails (Complete): backend/app/client_notices.py, backend/app/scheduling.py, backend/app/worker.py, backend/tests/test_client_notices.py
- 05-03 On-call API and portal appointments (Complete): backend/app/main.py, backend/app/oncall_service.py, backend/app/portal.py, backend/app/routers/oncall.py, backend/app/routers/portal.py, backend/tests/test_oncall_api.py, backend/tests/test_portal_appointments.py
- 05-04 Staff UI: email switch, on-call page, widget and board (Complete): frontend/src/App.tsx, frontend/src/OnCall.test.tsx, frontend/src/OnCallWidget.tsx, frontend/src/pages/Dispatch.tsx, frontend/src/pages/OnCall.tsx, frontend/src/pages/Settings.tsx, frontend/src/scheduling/BookingDialog.tsx, frontend/src/scheduling/EditDialog.tsx, frontend/src/scheduling/api.ts, frontend/src/scheduling/board.test.ts, frontend/src/scheduling/board.ts, frontend/src/scheduling/dispatch.css, frontend/src/scheduling/oncall.ts
- 05-05 Portal appointments page, docs and verify checklist (Complete)

## Decisions
- 05-02: `send_due` returns the number of emails queued, not the number of rows processed. Skipped rows are not counted.
- 05-02: Outbound rows are created with `auto_generated=True`, so `send_pending` adds the auto-reply headers, as autoreply and csat mail already do.
- 05-02: Skipped notices are not audited. Only sent ones get an `appointment_notice.send` audit row.
- 05-03: Invalid input (unknown or inactive users, anchor not on the handoff weekday, bad window) raises InvalidOncall, which the router returns as 422.
- 05-03: Overrides accept any active user, not only rotation members. An override for a user later removed from the rotation still applies, and a test covers it.
- 05-03: A schedule window of exactly 31 days is accepted; one second over is 422. start and end must carry a timezone offset.
- 05-04: The booking payload omits notify_client unless the box is ticked, so it sends `notify_client: false` or nothing. The server default is true, and always sending 
- 05-04: frontend/src/api.ts (forbidden) has no appointment_emails_enabled in AppSettings, so the Settings card widens the type locally.
- 05-04: A shift's rotation name comes from a separate /oncall/rotations query, because ShiftOut carries no rotation name.
- 05-05: Upcoming means an appointment that has not ended yet. It is sorted soonest first. Past ones are sorted most recent first. The backend already limits results to 

## Conventions and Open Questions
- 05-01 convention: Later waves can use `app.oncall.who_is_on(rotation, members, overrides, at, tz)` and `app.oncall.shifts(rotation, members, overrides, start, end, tz)`.
- 05-01 convention: `settings.appointment_emails_enabled` defaults to false and `appointments.notify_client` defaults to true.
- 05-02 convention: `client_notices.latest_for(db, ids)` returns a `dict[int, ClientNoticeOut]` and applies RLS from the session scope.
- 05-02 convention: 05-03 runs pytest against the same `psa_test` database, because `conftest` drops the schema at session start. Parallel runs could interfere with each other.
- 05-03 convention: Routes: GET/POST /api/oncall/rotations, PATCH /api/oncall/rotations/{id}, GET/POST /api/oncall/rotations/{id}/overrides, DELETE /api/oncall/overrides/{id}, GET 
- 05-03 convention: oncall_service.now(ctx, at=None) and schedule(ctx, start, end) are reusable by later waves.
- 05-04 convention: Routes used: GET/POST /api/oncall/rotations, PATCH /api/oncall/rotations/{id}, GET/POST /api/oncall/rotations/{id}/overrides, DELETE /api/oncall/overrides/{id},
- 05-04 convention: `backgroundBlocks(availability, zone, range, shifts?, rotationNames?)` is backward compatible.
- 05-04 convention: AppSettings in frontend/src/api.ts could gain appointment_emails_enabled in a later plan.
- 05-05 convention: The portal route is `/portal/appointments`, with query key `["portal","appointments"]`.
- 05-05 convention: `.planning/VERIFY.md` now lists the Phase 5 checks for Phase 14.

## Files Modified
| File | Change |
|------|--------|
| `backend/app/client_notices.py` | 05-02: Client appointment emails |
| `backend/app/scheduling.py` | 05-02: Client appointment emails |
| `backend/app/worker.py` | 05-02: Client appointment emails |
| `backend/tests/test_client_notices.py` | 05-02: Client appointment emails |
| `backend/app/main.py` | 05-03: On-call API and portal appointments |
| `backend/app/oncall_service.py` | 05-03: On-call API and portal appointments |
| `backend/app/portal.py` | 05-03: On-call API and portal appointments |
| `backend/app/routers/oncall.py` | 05-03: On-call API and portal appointments |
| `backend/app/routers/portal.py` | 05-03: On-call API and portal appointments |
| `backend/tests/test_oncall_api.py` | 05-03: On-call API and portal appointments |
| `backend/tests/test_portal_appointments.py` | 05-03: On-call API and portal appointments |
| `frontend/src/App.tsx` | 05-04: Staff UI: email switch, on-call page, widget and board |
| `frontend/src/OnCall.test.tsx` | 05-04: Staff UI: email switch, on-call page, widget and board |
| `frontend/src/OnCallWidget.tsx` | 05-04: Staff UI: email switch, on-call page, widget and board |
| `frontend/src/pages/Dispatch.tsx` | 05-04: Staff UI: email switch, on-call page, widget and board |
| `frontend/src/pages/OnCall.tsx` | 05-04: Staff UI: email switch, on-call page, widget and board |
| `frontend/src/pages/Settings.tsx` | 05-04: Staff UI: email switch, on-call page, widget and board |
| `frontend/src/scheduling/BookingDialog.tsx` | 05-04: Staff UI: email switch, on-call page, widget and board |
| `frontend/src/scheduling/EditDialog.tsx` | 05-04: Staff UI: email switch, on-call page, widget and board |
| `frontend/src/scheduling/api.ts` | 05-04: Staff UI: email switch, on-call page, widget and board |
| `frontend/src/scheduling/board.test.ts` | 05-04: Staff UI: email switch, on-call page, widget and board |
| `frontend/src/scheduling/board.ts` | 05-04: Staff UI: email switch, on-call page, widget and board |
| `frontend/src/scheduling/dispatch.css` | 05-04: Staff UI: email switch, on-call page, widget and board |
| `frontend/src/scheduling/oncall.ts` | 05-04: Staff UI: email switch, on-call page, widget and board |

## Verification
- 05-01 (REQ-05): 5/5 verification commands passed
- 05-02 (REQ-05): 5/5 verification commands passed
- 05-03 (REQ-05): 5/5 verification commands passed
- 05-04 (REQ-05): 3/3 verification commands passed
- 05-05 (REQ-05): 4/4 verification commands passed

## Agents
- 05-01: engineering-backend-architect
- 05-02: engineering-backend-architect
- 05-03: engineering-senior-developer
- 05-04: engineering-frontend-developer
- 05-05: engineering-frontend-developer

## Also Covered
- backend/alembic/versions/0026_client_notices_oncall.py
- backend/app/models.py
- backend/app/scheduling_schemas.py
- backend/app/schemas.py
- backend/app/oncall_schemas.py
- backend/app/oncall.py
- backend/tests/test_client_notices_oncall_schema.py
- backend/tests/test_oncall_math.py
- frontend/src/portal/PortalApp.tsx
- frontend/src/portal/AppointmentsPage.tsx
- frontend/src/portal/appointments.ts
- frontend/src/PortalAppointments.test.tsx
- docs/SCHEDULING.md
- docs/PORTAL.md
- docs/verify/client-notices-oncall.md
