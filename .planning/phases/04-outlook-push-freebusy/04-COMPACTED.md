---
phase: 04-outlook-push-freebusy
compacted: 2026-10-10
original_summaries: [04-01-SUMMARY.md, 04-02-SUMMARY.md, 04-03-SUMMARY.md, 04-04-SUMMARY.md]
requirements_satisfied: [REQ-04]
---

# Phase 4: Outlook push + free/busy — Compacted Summary

## Deliverables
- 04-01 Graph calendar client, fake Graph calendar endpoints and the tenant spike script (Complete): backend/app/mail/graph.py, backend/dev/fake_graph.py, backend/dev/graph_calendar_spike.py, backend/tests/test_graph_calendar.py
- 04-02 Sync schema, outbox enqueue and the worker push job (Complete): backend/alembic/versions/0025_outlook_sync.py, backend/app/calendar_sync.py, backend/app/models.py, backend/app/scheduling.py, backend/app/worker.py, backend/tests/test_calendar_sync.py, backend/tests/test_calendar_sync_schema.py
- 04-03 Free/busy cache job and the sync status, retry and availability API (Complete with Warnings)
- 04-04 Board Outlook busy shading, sync badges, settings card and setup docs (Complete): docs/CALENDAR_SETUP.md, docs/MAIL_SETUP.md, frontend/e2e/dispatch.spec.ts, frontend/src/OutlookSync.test.tsx, frontend/src/pages/Dispatch.tsx, frontend/src/pages/Settings.tsx, frontend/src/scheduling/EditDialog.tsx, frontend/src/scheduling/api.ts, frontend/src/scheduling/board.test.ts, frontend/src/scheduling/board.ts, frontend/src/scheduling/dispatch.css

## Decisions
- 04-01: The spike treats only 401 or 403 from `--outside` as PASS. Any other status gives WARN, and so does a successful read.
- 04-01: A getSchedule entry with an error object maps to `[]` and is logged at WARNING, as the plan says.
- 04-01: The spike inserts `backend/` into `sys.path` so it runs as `python dev/graph_calendar_spike.py` from `backend/`.
- 04-02: A claimed row is leased: `next_attempt_at` moves forward 10 minutes and the row lock is released before any Graph call. Appointment writes never wait on Graph, 
- 04-02: The result is written under a fresh row lock. If `desired_version` changed during the push, the row stays pending; the event id, tech and generation are still s
- 04-02: `set_org_scope` is transaction-local, so `push_pending` sets `'all'` itself before every transaction. It commits once per row.
- 04-03: `routers/config.py` and `test_zz_api_contract.py` are unchanged. `PATCH /settings` forwards every sent field through `update_settings`, so `outlook_sync_enabled
- 04-03: An appointment with no sync row shows `skipped` when sync is enabled.
- 04-04: `scripts/e2e.sh` is unchanged; the new test needed nothing from it.
- 04-04: The Settings toggle is shown only when `me.role === "admin"`; everyone else sees on/off text. It reads `enabled` from `GET /calendar-sync/status` and sends `PAT
- 04-04: The caption uses the oldest `outlook_fetched_at` among the rows shown. If any shown tech was never fetched, it reads "Outlook busy not loaded yet".

## Conventions and Open Questions
- 04-01 convention: `GraphError.transient` is the retry signal for later plans: True for network errors, 429 and 5xx.
- 04-01 convention: get_schedule returns lowercased keys, and delete_event swallows only a 404.
- 04-01 convention: `fake_graph.py` has `/_fail {"path_contains","status","count"}` for trying retries locally.
- 04-02 convention: `push_pending` and `enqueue` are in `/home/user/custom-psa-nolegion/backend/app/calendar_sync.py`. `FakeCalendarClient` in `tests/test_calendar_sync.py` is a mo
- 04-02 convention: Rows sit in 'pending' while `outlook_sync_enabled` is false
- 04-02 convention: enabling the setting drains them.
- 04-03 convention: `calendar_sync.eligible_users()` defines the polled set (active, role grants `schedule:write`, email present). Both `refresh_busy` and the status counts use it.
- 04-03 convention: `busy_fetched_at` on the status endpoint is the oldest fetch across the polled users.
- 04-04 convention: Frontend contract: `Appointment.sync` is read defensively (`sync?.state`) and `outlook_busy` is read as `?? []`, so older fixtures and mocks still work.
- 04-04 convention: `OutlookSyncCard` is exported from `pages/Settings.tsx`
- 04-04 convention: the board and the card share the `schedulingKeys.syncStatus()` query.

## Files Modified
| File | Change |
|------|--------|
| `backend/app/mail/graph.py` | 04-01: Graph calendar client, fake Graph calendar endpoints and the tenant spike script |
| `backend/dev/fake_graph.py` | 04-01: Graph calendar client, fake Graph calendar endpoints and the tenant spike script |
| `backend/dev/graph_calendar_spike.py` | 04-01: Graph calendar client, fake Graph calendar endpoints and the tenant spike script |
| `backend/tests/test_graph_calendar.py` | 04-01: Graph calendar client, fake Graph calendar endpoints and the tenant spike script |
| `backend/alembic/versions/0025_outlook_sync.py` | 04-02: Sync schema, outbox enqueue and the worker push job |
| `backend/app/calendar_sync.py` | 04-02: Sync schema, outbox enqueue and the worker push job |
| `backend/app/models.py` | 04-02: Sync schema, outbox enqueue and the worker push job |
| `backend/app/scheduling.py` | 04-02: Sync schema, outbox enqueue and the worker push job |
| `backend/app/worker.py` | 04-02: Sync schema, outbox enqueue and the worker push job |
| `backend/tests/test_calendar_sync.py` | 04-02: Sync schema, outbox enqueue and the worker push job |
| `backend/tests/test_calendar_sync_schema.py` | 04-02: Sync schema, outbox enqueue and the worker push job |
| `docs/CALENDAR_SETUP.md` | 04-04: Board Outlook busy shading, sync badges, settings card and setup docs |
| `docs/MAIL_SETUP.md` | 04-04: Board Outlook busy shading, sync badges, settings card and setup docs |
| `frontend/e2e/dispatch.spec.ts` | 04-04: Board Outlook busy shading, sync badges, settings card and setup docs |
| `frontend/src/OutlookSync.test.tsx` | 04-04: Board Outlook busy shading, sync badges, settings card and setup docs |
| `frontend/src/pages/Dispatch.tsx` | 04-04: Board Outlook busy shading, sync badges, settings card and setup docs |
| `frontend/src/pages/Settings.tsx` | 04-04: Board Outlook busy shading, sync badges, settings card and setup docs |
| `frontend/src/scheduling/EditDialog.tsx` | 04-04: Board Outlook busy shading, sync badges, settings card and setup docs |
| `frontend/src/scheduling/api.ts` | 04-04: Board Outlook busy shading, sync badges, settings card and setup docs |
| `frontend/src/scheduling/board.test.ts` | 04-04: Board Outlook busy shading, sync badges, settings card and setup docs |
| `frontend/src/scheduling/board.ts` | 04-04: Board Outlook busy shading, sync badges, settings card and setup docs |
| `frontend/src/scheduling/dispatch.css` | 04-04: Board Outlook busy shading, sync badges, settings card and setup docs |

## Verification
- 04-01 (REQ-04): 5/5 verification commands passed
- 04-02 (REQ-04): 6/6 verification commands passed
- 04-03 (REQ-04): 6/6 verification commands passed
- 04-04 (REQ-04): 6/6 verification commands passed

## Agents
- 04-01: engineering-backend-architect
- 04-02: engineering-backend-architect
- 04-03: engineering-backend-architect
- 04-04: engineering-frontend-developer

## Also Covered
- backend/app/scheduling_schemas.py
- backend/app/routers/scheduling.py
- backend/app/routers/config.py
- backend/app/schemas.py
- backend/tests/test_calendar_busy.py
- backend/tests/test_calendar_sync_api.py
- backend/tests/test_zz_api_contract.py
- docs/SCHEDULING.md
