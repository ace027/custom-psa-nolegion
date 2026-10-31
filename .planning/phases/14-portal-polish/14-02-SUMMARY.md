# Plan 14-02 Summary: Portal attachments, contact self-service and CSV export (backend)

## Result
**Status**: Complete
**Wave**: 2
**Agent**: engineering-backend-architect
**Completed**: 2026-10-31

## Agent Selection Rationale

| Candidate | Semantic | Heuristic | Memory | Total | Source |
|-----------|----------|-----------|--------|-------|--------|
| engineering-backend-architect | — | 11 | 2.92 | 13.92 | mandatory |
| engineering-senior-developer | — | 20 | 2.91 | 22.91 | heuristic |
| testing-qa-verification-specialist | — | 14 | 3.15 | 17.15 | heuristic |

- **Task type detected**: implementation
- **Confidence**: LOW
- **Adapter**: claude-code
- **Model tier**: sonnet

## Completed Tasks
- [x] Task 1: Portal attachments (done)
- [x] Task 2: Contact self-service and CSV export (done)
- [x] Task 3: Tests, docs and spec (done)

## Files Modified
- `backend/app/portal.py`
- `backend/app/portal_files.py`
- `backend/app/portal_schemas.py`
- `backend/app/repositories.py`
- `backend/app/routers/portal.py`
- `backend/app/schemas.py`
- `backend/tests/test_portal_polish.py`
- `backend/tests/test_tickets.py`
- `docs/PORTAL.md`
- `docs/api/openapi.json`

## Verification Results
6/6 verification commands passed (run by Triad after the agent finished).

## Verification Commands
| Command | Exit Code | Result |
|---------|-----------|--------|
| `cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/python -m pytest -q tests/test_portal_polish.py tests/test_portal_sso.py tests/test_portal.py tests/test_tickets.py tests/test_isolation.py tests/test_api_v1_and_openapi.py tests/test_zz_api_contract.py` | 0 | PASS |
| `cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/python -W ignore -m app.openapi_export --check` | 0 | PASS |
| `cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/ruff check app tests && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/ruff format --check app tests` | 0 | PASS |
| `cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/python -W ignore -c "from app.main import app; ps=app.openapi()['paths']; assert '/api/v1/portal/tickets/{ticket_id}/attachments' in ps and '/api/v1/portal/attachments/{attachment_id}/download' in ps"` | 0 | PASS |
| `cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/python -W ignore -c "from app.main import app; ps=app.openapi()['paths']; assert all(p in ps for p in ['/api/v1/portal/me/contact','/api/v1/portal/export/tickets.csv','/api/v1/portal/export/invoices.csv','/api/v1/portal/export/devices.csv'])"` | 0 | PASS |
| `cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/python -m pytest -q tests/test_portal_polish.py` | 0 | PASS |

## Key Decisions
- Only a ticket with status `closed` refuses uploads; `resolved` and `waiting_on_customer` accept them.
- The extension allow-list is txt, log, csv, pdf, png, jpg, jpeg, gif, webp, doc, docx, xls, xlsx, ppt, pptx, zip, eml, msg. Anything else is 415.
- The oversized-body check runs on the encoded length before decoding, as the plan asked.
- The tickets export "status" column uses the status label (`status_ref.name`) and "priority" uses `priority.name`.
- The invoices export reads `invoice_date` as `issue_date` and uses the payment status. `total` and `balance` are money columns.

## Issues Encountered
- My new `test_tickets.py` test first wrote into the real `backend/data/` directory. I redirected it to a temp dir and deleted the stray folder.
- `.planning/memory/PREFERENCES.md` shows as modified in `git status`. I did not touch it.

## Escalations
(none)

## Handoff Context
- **Key outputs**: backend/app/portal.py; backend/app/portal_files.py; backend/app/portal_schemas.py; backend/app/repositories.py; backend/app/routers/portal.py; backend/app/schemas.py; backend/tests/test_portal_polish.py; backend/tests/test_tickets.py; docs/PORTAL.md; docs/api/openapi.json
- **Decisions made**: Only a ticket with status `closed` refuses uploads; `resolved` and `waiting_on_customer` accept them.; The extension allow-list is txt, log, csv, pdf, png, jpg, jpeg, gif, webp, doc, docx, xls, xlsx, ppt, pptx, zip, eml, msg. Anything else is 415.; The oversized-body check runs on the encoded length before decoding, as the plan asked.; The tickets export "status" column uses the status label (`status_ref.name`) and "priority" uses `priority.name`.; The invoices export reads `invoice_date` as `issue_date` and uses the payment status. `total` and `balance` are money columns.
- **Open questions**: (none)
- **Conventions established**: Portal uploads set `source='portal'`, `email_message_id=None` and `uploaded_by_contact_id`. Portal reads filter on `source='portal'`.; Tests that upload must redirect `attachments_dir` to a temp dir, as the autouse fixture in `test_portal_polish.py` does.

## Requirements Covered
- REQ-13

## Token Usage
24 requests, 1463009 input tokens (1384843 cached), 22983 output tokens, $0.7022
