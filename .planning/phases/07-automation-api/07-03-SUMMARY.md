# Plan 07-03 Summary: Events and signed outbound webhooks (generic, Teams, n8n)

## Result
**Status**: Complete
**Wave**: 3
**Agent**: engineering-backend-architect
**Completed**: 2026-10-21

## Agent Selection Rationale

| Candidate | Semantic | Heuristic | Memory | Total | Source |
|-----------|----------|-----------|--------|-------|--------|
| engineering-backend-architect | — | 18 | 3.01 | 21.009999999999998 | mandatory |
| engineering-senior-developer | — | 27 | 3.08 | 30.08 | heuristic |
| testing-qa-verification-specialist | — | 13 | 3.61 | 16.61 | heuristic |

- **Task type detected**: implementation
- **Confidence**: LOW
- **Adapter**: claude-code
- **Model tier**: sonnet

## Completed Tasks
- [x] Task 1: Event emission and webhook outbox (done)
- [x] Task 2: Webhook routes and docs (done)
- [x] Task 3: Webhooks page (done)

## Files Modified
- `backend/app/config.py`
- `backend/app/events.py`
- `backend/app/main.py`
- `backend/app/notifications.py`
- `backend/app/rmm_alerts.py`
- `backend/app/routers/webhooks.py`
- `backend/app/schemas.py`
- `backend/app/ticket_services.py`
- `backend/app/webhooks.py`
- `backend/app/worker.py`
- `backend/tests/test_events.py`
- `backend/tests/test_webhooks.py`
- `backend/tests/test_webhooks_api.py`
- `docs/WEBHOOKS.md`
- `frontend/src/App.tsx`
- `frontend/src/Webhooks.test.tsx`
- `frontend/src/api.ts`
- `frontend/src/pages/Webhooks.tsx`

## Verification Results
6/6 verification commands passed (run by Triad after the agent finished).

## Verification Commands
| Command | Exit Code | Result |
|---------|-----------|--------|
| `service postgresql start >/dev/null 2>&1; cd backend && ruff check app tests && ruff format --check app tests` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_events.py tests/test_webhooks.py tests/test_webhooks_api.py tests/test_tickets.py tests/test_notifications.py tests/test_rmm_alerts.py tests/test_api_keys.py` | 0 | PASS |
| `cd frontend && npm run typecheck && npx vitest run && npm run build` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_events.py tests/test_webhooks.py` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_webhooks_api.py` | 0 | PASS |
| `cd frontend && npm run typecheck && npx vitest run src/Webhooks.test.tsx` | 0 | PASS |

## Key Decisions
- Rows are locked and committed one at a time in deliver_due (ids selected first, then FOR UPDATE SKIP LOCKED per row), because a commit per row would release a lock taken on the whole batch.
- emit() queues inside a savepoint and logs any failure, so an outbox problem never undoes a ticket change.
- sla_breached_event_at is stamped with a core update that keeps updated_at, so the breach bookkeeping does not look like an edit.
- A DNS failure at save time returns 409 "DNS lookup failed". Test pings to a disabled endpoint return 409.
- Event and kind validation is done in the service (409), not by pydantic Literals. Webhook URLs must be https even with the private-host opt-in.
- The signature is HMAC-SHA256 over "<timestamp>.<raw body>".

## Issues Encountered
- Tests that monkeypatch socket.getaddrinfo must let localhost through, or the Postgres connection times out. test_webhooks.py handles this with a LOCAL set.
- ticket.customer_reply does not also emit status_changed when the reply reopens the ticket. The plan lists only customer_reply for that path.

## Escalations
(none)

## Handoff Context
- **Key outputs**: backend/app/config.py; backend/app/events.py; backend/app/main.py; backend/app/notifications.py; backend/app/rmm_alerts.py; backend/app/routers/webhooks.py; backend/app/schemas.py; backend/app/ticket_services.py; backend/app/webhooks.py; backend/app/worker.py; backend/tests/test_events.py; backend/tests/test_webhooks.py; backend/tests/test_webhooks_api.py; docs/WEBHOOKS.md; frontend/src/App.tsx; frontend/src/Webhooks.test.tsx; frontend/src/api.ts; frontend/src/pages/Webhooks.tsx
- **Decisions made**: Rows are locked and committed one at a time in deliver_due (ids selected first, then FOR UPDATE SKIP LOCKED per row), because a commit per row would release a lock taken on the whole batch.; emit() queues inside a savepoint and logs any failure, so an outbox problem never undoes a ticket change.; sla_breached_event_at is stamped with a core update that keeps updated_at, so the breach bookkeeping does not look like an edit.; A DNS failure at save time returns 409 "DNS lookup failed". Test pings to a disabled endpoint return 409.; Event and kind validation is done in the service (409), not by pydantic Literals. Webhook URLs must be https even with the private-host opt-in.; The signature is HMAC-SHA256 over "<timestamp>.<raw body>".
- **Open questions**: (none)
- **Conventions established**: Plan 07-04 registers into events.RULE_HOOK, called as hook(ctx, type, event_id, ticket, alert, changes), and runs only when events.automation_depth is 0.; Rule actions should raise automation_depth while they run. Webhooks still fire at any depth.; tests.test_webhooks exports add_endpoint, queue, deliver and sample_body for reuse.; Run the full backend suite once before commit to confirm test_zz_api_contract sees all seven webhook routes hit.

## Requirements Covered
- REQ-07

## Token Usage
36 requests, 3601033 input tokens (3310033 cached), 56628 output tokens, $1.9558
