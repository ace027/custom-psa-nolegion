# Plan 07-04 Summary: Rules engine with dry run, trace and loop guard

## Result
**Status**: Partial
**Wave**: 4
**Agent**: engineering-backend-architect
**Completed**: 2026-10-21

## Agent Selection Rationale

| Candidate | Semantic | Heuristic | Memory | Total | Source |
|-----------|----------|-----------|--------|-------|--------|
| engineering-backend-architect | — | 17 | 3.01 | 20.009999999999998 | mandatory |
| engineering-senior-developer | — | 20 | 3.08 | 23.08 | heuristic |
| testing-qa-verification-specialist | — | 13 | 3.61 | 16.61 | heuristic |

- **Task type detected**: implementation
- **Confidence**: LOW
- **Adapter**: claude-code
- **Model tier**: sonnet

## Completed Tasks
- [x] Task 1: Rules engine (done)
- [x] Task 2: Rule routes (done)
- [x] Task 3: Rule builder page and verify checklist (done)

## Files Modified
- `backend/app/automation.py`
- `backend/app/events.py`
- `backend/app/main.py`
- `backend/app/notifications.py`
- `backend/app/routers/automation.py`
- `backend/app/schemas.py`
- `backend/tests/test_automation.py`
- `backend/tests/test_automation_api.py`
- `docs/AUTOMATION.md`
- `docs/verify/automation-api.md`
- `frontend/src/App.tsx`
- `frontend/src/Automation.test.tsx`
- `frontend/src/api.ts`
- `frontend/src/pages/Automation.tsx`

## Verification Results
7/7 verification commands passed (run by Triad after the agent finished).

## Verification Commands
| Command | Exit Code | Result |
|---------|-----------|--------|
| `service postgresql start >/dev/null 2>&1; cd backend && ruff check app tests && ruff format --check app tests` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_automation.py tests/test_automation_api.py tests/test_events.py tests/test_webhooks.py tests/test_webhooks_api.py tests/test_api_keys.py tests/test_tickets.py tests/test_notifications.py tests/test_rmm_alerts.py` | 0 | PASS |
| `cd frontend && npm run typecheck && npx vitest run && npm run build` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_automation.py tests/test_events.py tests/test_notifications.py` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_automation_api.py` | 0 | PASS |
| `cd frontend && npm run typecheck && npx vitest run src/Automation.test.tsx` | 0 | PASS |
| `grep -q 'Phase 7' .planning/VERIFY.md && test -f docs/verify/automation-api.md` | 0 | PASS |

## Key Decisions
- on_event is called directly from events.emit instead of being appended to RULE_HOOK. tests/test_events.py (outside my file list) asserts RULE_HOOK == [], so import-time registration would break it. RULE_HOOK still works for extra hooks.
- A rule's notify email is stored with event 'assigned' in staff_notifications. The 0028 CHECK constraint only allows four events and I may not touch migrations. Its dedupe key starts with "rule:".
- The rate cap counts only matched, non-dry runs in the last hour.
- Dry run of a saved rule skips validate(). Dry-run action statuses are 'would_run' and 'would_skip'.

## Issues Encountered
- Rules that assign on ticket.created cause a second, duplicate ticket.assigned event at depth 0, so a rule on ticket.assigned can run. The cause is in ticket_services.create_ticket, which reads ticket.assignee_id after the created event has already run the rules. The loop-guard test uses a status_changed trigger to avoid this.

## Escalations
| # | Severity | Type | Decision | Status | Resolution |
|---|----------|------|----------|--------|------------|
| 1 | warning | out-of-scope file | Fix ticket_services.create_ticket by capturing assignee_id before emitting ticket.created, so rule changes do not produce a depth-0 ticket.assigned event. | pending | INVALID: type "out-of-scope file" is not one of architecture, dependency, scope, schema, api, deletion, infrastructure, quality |
| 2 | info | schema | Add 'rule_notify' to the staff_notifications event CHECK constraint in a new migration. | pending |  |

- #1 context: ticket_services.py is not in this plan's file list.
- #2 context: backend/alembic/ and models.py are forbidden for this plan, so notifications.py maps rule emails to 'assigned'.

## Handoff Context
- **Key outputs**: backend/app/automation.py; backend/app/events.py; backend/app/main.py; backend/app/notifications.py; backend/app/routers/automation.py; backend/app/schemas.py; backend/tests/test_automation.py; backend/tests/test_automation_api.py; docs/AUTOMATION.md; docs/verify/automation-api.md; frontend/src/App.tsx; frontend/src/Automation.test.tsx; frontend/src/api.ts; frontend/src/pages/Automation.tsx
- **Decisions made**: on_event is called directly from events.emit instead of being appended to RULE_HOOK. tests/test_events.py (outside my file list) asserts RULE_HOOK == [], so import-time registration would break it. RULE_HOOK still works for extra hooks.; A rule's notify email is stored with event 'assigned' in staff_notifications. The 0028 CHECK constraint only allows four events and I may not touch migrations. Its dedupe key starts with "rule:".; The rate cap counts only matched, non-dry runs in the last hour.; Dry run of a saved rule skips validate(). Dry-run action statuses are 'would_run' and 'would_skip'.
- **Open questions**: (none)
- **Conventions established**: Add 'rule_notify' to the ck_staff_notifications_event constraint in a later migration, then drop STORED_EVENT.; The create_ticket fix is to capture the assignee before the created emit.; test_zz_api_contract passed in the subset above, so the new routes are hit.

## Requirements Covered
- REQ-07

## Token Usage
51 requests, 5763976 input tokens (5599266 cached), 69075 output tokens, $2.2223
