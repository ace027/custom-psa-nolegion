# Plan 06-01 Summary: RMM alert schema, models and NinjaOne alert adapter

## Result
**Status**: Complete
**Wave**: 1
**Agent**: engineering-backend-architect
**Completed**: 2026-10-20

## Agent Selection Rationale

| Candidate | Semantic | Heuristic | Memory | Total | Source |
|-----------|----------|-----------|--------|-------|--------|
| engineering-backend-architect | — | 15 | 2.93 | 17.93 | mandatory |
| engineering-senior-developer | — | 19 | 2.91 | 21.91 | heuristic |
| testing-qa-verification-specialist | — | 13 | 3.53 | 16.53 | heuristic |

- **Task type detected**: implementation
- **Confidence**: LOW
- **Adapter**: claude-code
- **Model tier**: sonnet

## Completed Tasks
- [x] Task 1: Migration 0027 and models (done)
- [x] Task 2: Schema and privilege tests (done)
- [x] Task 3: NinjaOne list_alerts and fake vendor (done)

## Files Modified
- `backend/alembic/versions/0027_rmm_alerts.py`
- `backend/app/integrations/base.py`
- `backend/app/integrations/ninjaone.py`
- `backend/app/models.py`
- `backend/tests/conftest.py`
- `backend/tests/test_rmm_alerts_schema.py`
- `backend/tests/test_vendor_adapters.py`
- `backend/tests/vendorfakes.py`

## Verification Results
6/6 verification commands passed (run by Triad after the agent finished).

## Verification Commands
| Command | Exit Code | Result |
|---------|-----------|--------|
| `service postgresql start >/dev/null 2>&1; cd backend && ruff check app tests && ruff format --check app tests` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_rmm_alerts_schema.py tests/test_vendor_adapters.py tests/test_asset_sync.py tests/test_tickets.py tests/test_client_notices_oncall_schema.py` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && alembic upgrade head && alembic downgrade 0026 && alembic upgrade head` | 0 | PASS |
| `cd backend && grep -q 'rmm_alerts, asset_overrides' tests/conftest.py` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_rmm_alerts_schema.py` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_vendor_adapters.py tests/test_asset_sync.py` | 0 | PASS |

## Key Decisions
- Downgrade first runs `UPDATE tickets SET source='ui' WHERE source='rmm'` so the restored 3-value check cannot fail on existing rows.
- `Ticket.asset_id` is a plain BigInteger column with no `ForeignKey`, because the composite FK lives only in the migration. The viewonly `Ticket.asset` and `RmmAlert` relationships use explicit `primaryjoin` and `foreign_keys`.
- The ruff formatter reformatted only the files in this plan, and I did not run `ruff format --check` separately afterwards.

## Issues Encountered
- `Ticket.asset` is `lazy='selectin'` as the plan specifies, so every ticket query now also loads the asset and its sources and overrides. This adds queries on ticket-heavy paths.
- `git status` shows `.planning/STATE.md` and `.planning/memory/PREFERENCES.md` as modified. I did not touch them.

## Escalations
(none)

## Handoff Context
- **Key outputs**: backend/alembic/versions/0027_rmm_alerts.py; backend/app/integrations/base.py; backend/app/integrations/ninjaone.py; backend/app/models.py; backend/tests/conftest.py; backend/tests/test_rmm_alerts_schema.py; backend/tests/test_vendor_adapters.py; backend/tests/vendorfakes.py
- **Decisions made**: Downgrade first runs `UPDATE tickets SET source='ui' WHERE source='rmm'` so the restored 3-value check cannot fail on existing rows.; `Ticket.asset_id` is a plain BigInteger column with no `ForeignKey`, because the composite FK lives only in the migration. The viewonly `Ticket.asset` and `RmmAlert` relationships use explicit `primaryjoin` and `foreign_keys`.; The ruff formatter reformatted only the files in this plan, and I did not run `ruff format --check` separately afterwards.
- **Open questions**: (none)
- **Conventions established**: Use `registry.build_adapter` and `FakeVendor.alerts` / `fail_alerts` with the `alert(device, cond)` helper in `vendorfakes.py`. Its `condition_key` is `f"{device}:{cond}"`, which matches what `_to_alert` builds.; `rmm_alerts` has SELECT, INSERT and UPDATE for `psa_app` and no DELETE. Close an alert by setting `state='cleared'` together with `cleared_at` (the `ck_rmm_alerts_cleared` check requires both).; Inserting a second open row for the same `(integration_id, condition_key)` raises `uq_rmm_alerts_open`, so the poller should bump `occurrences` and `last_seen_at` instead.; `tickets.asset_id` and `rmm_alerts.asset_id` must belong to the same organization as the row, because the FKs are composite.

## Requirements Covered
- REQ-06
- SC1
- SC2

## Token Usage
11 requests, 431609 input tokens (379269 cached), 13207 output tokens, $0.3388
