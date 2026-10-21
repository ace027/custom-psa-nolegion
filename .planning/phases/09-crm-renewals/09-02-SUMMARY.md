# Plan 09-02 Summary: CRM service, quote link, forecast and renewal job

## Result
**Status**: Partial
**Wave**: 2
**Agent**: engineering-backend-architect
**Completed**: 2026-10-21

## Agent Selection Rationale

| Candidate | Semantic | Heuristic | Memory | Total | Source |
|-----------|----------|-----------|--------|-------|--------|
| engineering-backend-architect | — | 14 | 3.29 | 17.29 | mandatory |
| engineering-senior-developer | — | 20 | 3.14 | 23.14 | heuristic |
| testing-qa-verification-specialist | — | 13 | 3.83 | 16.83 | heuristic |

- **Task type detected**: implementation
- **Confidence**: LOW
- **Adapter**: claude-code
- **Model tier**: sonnet

## Completed Tasks
- [x] Task 1: Leads, opportunities, stages, forecast and quote hook (done)
- [x] Task 2: Renewal reminders job (done)
- [x] Task 3: Routes and API tests (done)

## Files Modified
- `backend/app/config_services.py`
- `backend/app/crm.py`
- `backend/app/crm_schemas.py`
- `backend/app/main.py`
- `backend/app/quoting.py`
- `backend/app/renewals.py`
- `backend/app/routers/crm.py`
- `backend/app/schemas.py`
- `backend/app/worker.py`
- `backend/tests/test_crm.py`
- `backend/tests/test_crm_api.py`
- `backend/tests/test_renewals.py`

## Verification Results
5/5 verification commands passed (run by Triad after the agent finished).

## Verification Commands
| Command | Exit Code | Result |
|---------|-----------|--------|
| `service postgresql start >/dev/null 2>&1; cd backend && ruff check app tests && ruff format --check app tests` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_crm.py tests/test_crm_api.py tests/test_renewals.py tests/test_quoting.py tests/test_crm_schema.py tests/test_notices.py tests/test_organizations.py` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_crm.py tests/test_quoting.py` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_renewals.py` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q tests/test_crm_api.py` | 0 | PASS |

## Key Decisions
- The forecast has an extra "later" bucket for close dates more than 12 months out, so the totals add up. Buckets run overdue, 12 months, later, no_date. A past close date counts as overdue; won this month and quarter come from closed_at in the business timezone.
- Activating an inactive won or lost stage deactivates the currently active one. Without that, the only active won or lost stage could never be swapped, because deactivating it is a 409.
- Deactivating the last active open stage is a 409.
- Only open quotes (draft, needs_approval, approved, sent) can be linked. The 409 text for a missing quote or one from another client is "different client".
- The scan creates a reminder for every lead time already reached, as the plan says. The first run at 29 days out creates both the 90 and the 30 reminder and one opportunity.
- The scan opens a new renewal opportunity only when there is no open one for that agreement. Each new reminder links to the open one.
- The accept-wins-opportunity test is in test_crm_api.py because tests/test_quoting.py is not on the writable list.

## Issues Encountered
- The full-suite run did not finish, so test_zz_api_contract still needs a pass. Run `cd backend && python -m pytest -q tests`, which takes over 10 minutes.

## Escalations
(none)

## Handoff Context
- **Key outputs**: backend/app/config_services.py; backend/app/crm.py; backend/app/crm_schemas.py; backend/app/main.py; backend/app/quoting.py; backend/app/renewals.py; backend/app/routers/crm.py; backend/app/schemas.py; backend/app/worker.py; backend/tests/test_crm.py; backend/tests/test_crm_api.py; backend/tests/test_renewals.py
- **Decisions made**: The forecast has an extra "later" bucket for close dates more than 12 months out, so the totals add up. Buckets run overdue, 12 months, later, no_date. A past close date counts as overdue; won this month and quarter come from closed_at in the business timezone.; Activating an inactive won or lost stage deactivates the currently active one. Without that, the only active won or lost stage could never be swapped, because deactivating it is a 409.; Deactivating the last active open stage is a 409.; Only open quotes (draft, needs_approval, approved, sent) can be linked. The 409 text for a missing quote or one from another client is "different client".; The scan creates a reminder for every lead time already reached, as the plan says. The first run at 29 days out creates both the 90 and the 30 reminder and one opportunity.; The scan opens a new renewal opportunity only when there is no open one for that agreement. Each new reminder links to the open one.; The accept-wins-opportunity test is in test_crm_api.py because tests/test_quoting.py is not on the writable list.
- **Open questions**: (none)
- **Conventions established**: API output shapes are in app/crm_schemas.py. The forecast response has buckets (keyed overdue, YYYY-MM, later, no_date), total, won_this_month and won_this_quarter.; GET /api/crm/stages returns inactive stages too.; Settings GET and PATCH now carry renewal_reminder_days (stored sorted descending) and renewal_email ("" clears it).; renewals.scan returns counts for reminders, opportunities, emails and done.

## Requirements Covered
- REQ-09

## Token Usage
31 requests, 2681728 input tokens (2187448 cached), 53420 output tokens, $2.2074
