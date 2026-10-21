---
phase: 07-automation-api
compacted: 2026-10-21
original_summaries: [07-01-SUMMARY.md, 07-02-SUMMARY.md, 07-03-SUMMARY.md, 07-04-SUMMARY.md]
requirements_satisfied: [REQ-07]
---

# Phase 7: Automation & API — Compacted Summary

## Deliverables
- 07-01 Automation & API schema, models and permissions (Complete): backend/alembic/versions/0028_automation_api.py, backend/app/models.py, backend/app/permissions.py, backend/tests/conftest.py, backend/tests/test_automation_schema.py, backend/tests/test_permissions.py
- 07-02 API keys: hashed, scoped, revocable bearer auth (Complete): backend/app/api_keys.py, backend/app/audit.py, backend/app/context.py, backend/app/deps.py, backend/app/main.py, backend/app/routers/api_keys.py, backend/app/schemas.py, backend/tests/test_api_keys.py, docs/API_KEYS.md, frontend/src/ApiKeys.test.tsx, frontend/src/App.tsx, frontend/src/api.ts, frontend/src/pages/ApiKeys.tsx
- 07-03 Events and signed outbound webhooks (generic, Teams, n8n) (Complete): backend/app/config.py, backend/app/events.py, backend/app/main.py, backend/app/notifications.py, backend/app/rmm_alerts.py, backend/app/routers/webhooks.py, backend/app/schemas.py, backend/app/ticket_services.py, backend/app/webhooks.py, backend/app/worker.py, backend/tests/test_events.py, backend/tests/test_webhooks.py, backend/tests/test_webhooks_api.py, docs/WEBHOOKS.md, frontend/src/App.tsx, frontend/src/Webhooks.test.tsx, frontend/src/api.ts, frontend/src/pages/Webhooks.tsx
- 07-04 Rules engine with dry run, trace and loop guard (Complete)

## Decisions
- 07-01: The `ApiKey.user` relationship sets `foreign_keys=[user_id]` because the table has two FKs to users.
- 07-01: `automation_rules` gets two CHECKs beyond the plan: `trigger <> ''` and `fire_count >= 0`.
- 07-01: The migration grants `USAGE, SELECT` on all sequences, as the plan said for sequences.
- 07-02: Sync FastAPI dependencies and handlers run in separate thread contexts, so a ContextVar set in the dependency never reached the handler. The key id is also stor
- 07-02: The dependency commits right after a successful `authenticate`, so the throttled `last_used_at` update is kept even when the request is then refused with 403.
- 07-02: A rejected key leaves one `auth.api_key_rejected` audit row. It holds only the 8-character prefix, never the token.
- 07-03: Rows are locked and committed one at a time in deliver_due (ids selected first, then FOR UPDATE SKIP LOCKED per row), because a commit per row would release a l
- 07-03: emit() queues inside a savepoint and logs any failure, so an outbox problem never undoes a ticket change.
- 07-03: sla_breached_event_at is stamped with a core update that keeps updated_at, so the breach bookkeeping does not look like an edit.
- 07-04: none new. I did not re-review the earlier code line by line. I only ran the tests and checks.

## Conventions and Open Questions
- 07-01 convention: Webhook delivery and automation-run uniqueness is enforced by `uq_webhook_deliveries_event` and the partial index `uq_automation_runs_event` (`WHERE NOT dry_run
- 07-01 convention: `psa_app` has no DELETE on the new tables, so archive or revoke by setting columns such as `archived_at` and `revoked_at`.
- 07-01 convention: Ticket source `'rule'` is allowed. The `Ticket.source` column is String(10), which fits.
- 07-02 convention: Later code can read `ctx.api_key_id` and `db.info["api_key_id"]` to tell whether a request came from an API key.
- 07-02 convention: Handlers that use `authenticated()` refuse API keys with 403, so any new endpoint a key should reach needs `require(<perm>)`.
- 07-02 convention: Keys can only be granted permissions that appear in MATRIX and are not in `KEY_FORBIDDEN`.
- 07-03 convention: Plan 07-04 registers into events.RULE_HOOK, called as hook(ctx, type, event_id, ticket, alert, changes), and runs only when events.automation_depth is 0.
- 07-03 convention: Rule actions should raise automation_depth while they run. Webhooks still fire at any depth.
- 07-03 convention: tests.test_webhooks exports add_endpoint, queue, deliver and sample_body for reuse.
- 07-04 convention: Rules run only at automation_depth 0, and rule actions raise the depth while they run. Webhooks still fire at any depth.
- 07-04 convention: Run the owner checklist in docs/verify/automation-api.md. The real Teams Workflows URL, the real n8n instance and the LAN n8n (WEBHOOK_ALLOW_PRIVATE_HOSTS) are 

## Files Modified
| File | Change |
|------|--------|
| `backend/alembic/versions/0028_automation_api.py` | 07-01: Automation & API schema, models and permissions |
| `backend/app/models.py` | 07-01: Automation & API schema, models and permissions |
| `backend/app/permissions.py` | 07-01: Automation & API schema, models and permissions |
| `backend/tests/conftest.py` | 07-01: Automation & API schema, models and permissions |
| `backend/tests/test_automation_schema.py` | 07-01: Automation & API schema, models and permissions |
| `backend/tests/test_permissions.py` | 07-01: Automation & API schema, models and permissions |
| `backend/app/api_keys.py` | 07-02: API keys: hashed, scoped, revocable bearer auth |
| `backend/app/audit.py` | 07-02: API keys: hashed, scoped, revocable bearer auth |
| `backend/app/context.py` | 07-02: API keys: hashed, scoped, revocable bearer auth |
| `backend/app/deps.py` | 07-02: API keys: hashed, scoped, revocable bearer auth |
| `backend/app/main.py` | 07-02: API keys: hashed, scoped, revocable bearer auth |
| `backend/app/routers/api_keys.py` | 07-02: API keys: hashed, scoped, revocable bearer auth |
| `backend/app/schemas.py` | 07-02: API keys: hashed, scoped, revocable bearer auth |
| `backend/tests/test_api_keys.py` | 07-02: API keys: hashed, scoped, revocable bearer auth |
| `docs/API_KEYS.md` | 07-02: API keys: hashed, scoped, revocable bearer auth |
| `frontend/src/ApiKeys.test.tsx` | 07-02: API keys: hashed, scoped, revocable bearer auth |
| `frontend/src/App.tsx` | 07-02: API keys: hashed, scoped, revocable bearer auth |
| `frontend/src/api.ts` | 07-02: API keys: hashed, scoped, revocable bearer auth |
| `frontend/src/pages/ApiKeys.tsx` | 07-02: API keys: hashed, scoped, revocable bearer auth |
| `backend/app/config.py` | 07-03: Events and signed outbound webhooks (generic, Teams, n8n) |
| `backend/app/events.py` | 07-03: Events and signed outbound webhooks (generic, Teams, n8n) |
| `backend/app/main.py` | 07-03: Events and signed outbound webhooks (generic, Teams, n8n) |
| `backend/app/notifications.py` | 07-03: Events and signed outbound webhooks (generic, Teams, n8n) |
| `backend/app/rmm_alerts.py` | 07-03: Events and signed outbound webhooks (generic, Teams, n8n) |
| `backend/app/routers/webhooks.py` | 07-03: Events and signed outbound webhooks (generic, Teams, n8n) |
| `backend/app/schemas.py` | 07-03: Events and signed outbound webhooks (generic, Teams, n8n) |
| `backend/app/ticket_services.py` | 07-03: Events and signed outbound webhooks (generic, Teams, n8n) |
| `backend/app/webhooks.py` | 07-03: Events and signed outbound webhooks (generic, Teams, n8n) |
| `backend/app/worker.py` | 07-03: Events and signed outbound webhooks (generic, Teams, n8n) |
| `backend/tests/test_events.py` | 07-03: Events and signed outbound webhooks (generic, Teams, n8n) |
| `backend/tests/test_webhooks.py` | 07-03: Events and signed outbound webhooks (generic, Teams, n8n) |
| `backend/tests/test_webhooks_api.py` | 07-03: Events and signed outbound webhooks (generic, Teams, n8n) |
| `docs/WEBHOOKS.md` | 07-03: Events and signed outbound webhooks (generic, Teams, n8n) |
| `frontend/src/App.tsx` | 07-03: Events and signed outbound webhooks (generic, Teams, n8n) |
| `frontend/src/Webhooks.test.tsx` | 07-03: Events and signed outbound webhooks (generic, Teams, n8n) |
| `frontend/src/api.ts` | 07-03: Events and signed outbound webhooks (generic, Teams, n8n) |
| `frontend/src/pages/Webhooks.tsx` | 07-03: Events and signed outbound webhooks (generic, Teams, n8n) |

## Verification
- 07-01 (REQ-07): 6/6 verification commands passed
- 07-02 (REQ-07): 6/6 verification commands passed
- 07-03 (REQ-07): 6/6 verification commands passed
- 07-04 (REQ-07): 7/7 verification commands passed

## Agents
- 07-01: engineering-backend-architect
- 07-02: engineering-security-engineer
- 07-03: engineering-backend-architect
- 07-04: engineering-backend-architect

## Also Covered
- backend/app/automation.py
- backend/app/routers/automation.py
- backend/tests/test_automation.py
- backend/tests/test_automation_api.py
- frontend/src/pages/Automation.tsx
- frontend/src/Automation.test.tsx
- docs/AUTOMATION.md
- .planning/VERIFY.md
