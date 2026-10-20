---
phase: 06-rmm-alerts-to-tickets
compacted: 2026-10-20
original_summaries: [06-01-SUMMARY.md, 06-02-SUMMARY.md, 06-03-SUMMARY.md]
requirements_satisfied: [REQ-06, SC1, SC2, SC3]
---

# Phase 6: RMM alerts to tickets — Compacted Summary

## Deliverables
- 06-01 RMM alert schema, models and NinjaOne alert adapter (Complete): backend/alembic/versions/0027_rmm_alerts.py, backend/app/integrations/base.py, backend/app/integrations/ninjaone.py, backend/app/models.py, backend/tests/conftest.py, backend/tests/test_rmm_alerts_schema.py, backend/tests/test_vendor_adapters.py, backend/tests/vendorfakes.py
- 06-02 Alert polling engine, worker job and admin API (Complete): backend/app/asset_schemas.py, backend/app/integration_services.py, backend/app/rmm_alerts.py, backend/app/routers/integrations.py, backend/app/schemas.py, backend/app/ticket_services.py, backend/app/ticket_views.py, backend/app/worker.py, backend/tests/test_rmm_alerts.py, backend/tests/test_rmm_alerts_api.py
- 06-03 Integrations alerts panel, ticket device chip and verify docs (Complete): docs/verify/rmm-alerts.md, frontend/src/RmmAlerts.test.tsx, frontend/src/api.ts, frontend/src/pages/Integrations.tsx, frontend/src/pages/RmmAlertsCard.tsx, frontend/src/pages/TicketDetail.tsx

## Decisions
- 06-01: Downgrade first runs `UPDATE tickets SET source='ui' WHERE source='rmm'` so the restored 3-value check cannot fail on existing rows.
- 06-01: `Ticket.asset_id` is a plain BigInteger column with no `ForeignKey`, because the composite FK lives only in the migration. The viewonly `Ticket.asset` and `RmmA
- 06-01: The ruff formatter reformatted only the files in this plan, and I did not run `ruff format --check` separately afterwards.
- 06-02: A poll catches any adapter exception, not just `VendorError`. Non-vendor exceptions record only their type name, via `asset_sync._safe`, so a credential cannot 
- 06-02: When creating a ticket, the poller finds the newest earlier `RmmAlert` for the same condition and links the new ticket to its ticket as `related`. This covers b
- 06-02: `list_alerts` returns 409 for a bad `state` or `limit`. The router already validates both (422), so this only matters if the service is called directly.
- 06-03: Save sends PATCH `{config: {...existing, alerts_enabled, alert_min_severity, alert_clear_rule, alert_poll_minutes}}`. I assumed the existing integration PATCH a
- 06-03: The Ticket `asset_id` and `asset_name` fields and the integration alert fields are optional in the TypeScript types, so existing fixtures still compile.
- 06-03: "Last checked" uses a small `relTime` helper exported from `RmmAlertsCard.tsx`.

## Conventions and Open Questions
- 06-01 convention: Use `registry.build_adapter` and `FakeVendor.alerts` / `fail_alerts` with the `alert(device, cond)` helper in `vendorfakes.py`. Its `condition_key` is `f"{devic
- 06-01 convention: `rmm_alerts` has SELECT, INSERT and UPDATE for `psa_app` and no DELETE. Close an alert by setting `state='cleared'` together with `cleared_at` (the `ck_rmm_aler
- 06-01 convention: Inserting a second open row for the same `(integration_id, condition_key)` raises `uq_rmm_alerts_open`, so the poller should bump `occurrences` and `last_seen_a
- 06-02 convention: The poll lives at `rmm_alerts.poll(ctx, integration, adapter=None, now=None)` and returns a `PollResult`. Per-alert failures are counted in `failed`, and a vend
- 06-02 convention: The frontend can read the new `IntegrationOut` fields `alerts_polled_at`, `alerts_requested` and `alerts_last_error`. Config keys are `alerts_enabled`, `alert_m
- 06-02 convention: `GET /integrations/{id}/alerts?state=open|cleared|all&limit=1..500` returns `RmmAlertOut` newest first. `POST /integrations/{id}/alerts/poll` returns 202 with `
- 06-03 convention: `GET /integrations/{id}/alerts?state=` and `POST /integrations/{id}/alerts/poll` are used as 06-02 defined them. Resolution labels shown are resolved, noted and
- 06-03 convention: Phase 14 should confirm the NinjaOne alert field mapping against a live tenant first (check 0 in the checklist).

## Files Modified
| File | Change |
|------|--------|
| `backend/alembic/versions/0027_rmm_alerts.py` | 06-01: RMM alert schema, models and NinjaOne alert adapter |
| `backend/app/integrations/base.py` | 06-01: RMM alert schema, models and NinjaOne alert adapter |
| `backend/app/integrations/ninjaone.py` | 06-01: RMM alert schema, models and NinjaOne alert adapter |
| `backend/app/models.py` | 06-01: RMM alert schema, models and NinjaOne alert adapter |
| `backend/tests/conftest.py` | 06-01: RMM alert schema, models and NinjaOne alert adapter |
| `backend/tests/test_rmm_alerts_schema.py` | 06-01: RMM alert schema, models and NinjaOne alert adapter |
| `backend/tests/test_vendor_adapters.py` | 06-01: RMM alert schema, models and NinjaOne alert adapter |
| `backend/tests/vendorfakes.py` | 06-01: RMM alert schema, models and NinjaOne alert adapter |
| `backend/app/asset_schemas.py` | 06-02: Alert polling engine, worker job and admin API |
| `backend/app/integration_services.py` | 06-02: Alert polling engine, worker job and admin API |
| `backend/app/rmm_alerts.py` | 06-02: Alert polling engine, worker job and admin API |
| `backend/app/routers/integrations.py` | 06-02: Alert polling engine, worker job and admin API |
| `backend/app/schemas.py` | 06-02: Alert polling engine, worker job and admin API |
| `backend/app/ticket_services.py` | 06-02: Alert polling engine, worker job and admin API |
| `backend/app/ticket_views.py` | 06-02: Alert polling engine, worker job and admin API |
| `backend/app/worker.py` | 06-02: Alert polling engine, worker job and admin API |
| `backend/tests/test_rmm_alerts.py` | 06-02: Alert polling engine, worker job and admin API |
| `backend/tests/test_rmm_alerts_api.py` | 06-02: Alert polling engine, worker job and admin API |
| `docs/verify/rmm-alerts.md` | 06-03: Integrations alerts panel, ticket device chip and verify docs |
| `frontend/src/RmmAlerts.test.tsx` | 06-03: Integrations alerts panel, ticket device chip and verify docs |
| `frontend/src/api.ts` | 06-03: Integrations alerts panel, ticket device chip and verify docs |
| `frontend/src/pages/Integrations.tsx` | 06-03: Integrations alerts panel, ticket device chip and verify docs |
| `frontend/src/pages/RmmAlertsCard.tsx` | 06-03: Integrations alerts panel, ticket device chip and verify docs |
| `frontend/src/pages/TicketDetail.tsx` | 06-03: Integrations alerts panel, ticket device chip and verify docs |

## Verification
- 06-01 (REQ-06, SC1, SC2): 6/6 verification commands passed
- 06-02 (REQ-06, SC1, SC2, SC3): 5/5 verification commands passed
- 06-03 (REQ-06, SC2, SC3): 4/4 verification commands passed

## Agents
- 06-01: engineering-backend-architect
- 06-02: engineering-senior-developer
- 06-03: engineering-frontend-developer

## Also Covered
- .planning/VERIFY.md
