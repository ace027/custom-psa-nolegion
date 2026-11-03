# Plan 18-01 Summary: Accounting sender mailbox: setting, sending and clear errors

## Result
**Status**: Complete
**Wave**: 1
**Agent**: engineering-backend-architect
**Completed**: 2026-11-03

## Agent Selection Rationale

| Candidate | Semantic | Heuristic | Memory | Total | Source |
|-----------|----------|-----------|--------|-------|--------|
| engineering-backend-architect | — | 15 | 2.94 | 17.94 | mandatory |
| engineering-senior-developer | — | 26 | 3.07 | 29.07 | heuristic |
| testing-api-tester | — | 15 | 3.3 | 18.3 | heuristic |

- **Task type detected**: implementation
- **Confidence**: LOW
- **Adapter**: claude-code
- **Model tier**: sonnet

## Completed Tasks
- [x] Task 1: Schema, settings field and mailbox status (done)
- [x] Task 2: Graph send from another mailbox and permanent errors (done)
- [x] Task 3: Notices send from accounting; send_pending honours sender and fails clearly (done)

## Files Modified
- `backend/alembic/versions/0042_accounting_mailbox.py`
- `backend/app/mail/graph.py`
- `backend/app/mail/ingest.py`
- `backend/app/models.py`
- `backend/app/notices.py`
- `backend/app/routers/config.py`
- `backend/app/schemas.py`
- `backend/tests/mailfakes.py`
- `backend/tests/test_graph_client.py`
- `backend/tests/test_mail_ingest.py`
- `backend/tests/test_notices.py`
- `backend/tests/test_seed_and_migrations.py`
- `docs/api/openapi.json`

## Verification Results
7/7 verification commands passed (run by Triad after the agent finished).

## Verification Commands
| Command | Exit Code | Result |
|---------|-----------|--------|
| `cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/ruff check app tests` | 0 | PASS |
| `cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/ruff format --check app tests` | 0 | PASS |
| `cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/python -m app.openapi_export --check` | 0 | PASS |
| `cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/pytest -q -p no:warnings tests/test_graph_client.py tests/test_mail_ingest.py tests/test_notices.py tests/test_statements.py tests/test_invoice_emails.py tests/test_seed_and_migrations.py tests/test_api_v1_and_openapi.py` | 0 | PASS |
| `cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/pytest -q -p no:warnings tests/test_seed_and_migrations.py` | 0 | PASS |
| `cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/pytest -q -p no:warnings tests/test_graph_client.py` | 0 | PASS |
| `cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/pytest -q -p no:warnings tests/test_mail_ingest.py tests/test_notices.py tests/test_statements.py tests/test_invoice_emails.py` | 0 | PASS |

## Key Decisions
- config_services.update_settings is not in my file list and skips None values, so an "empty string becomes None" validator could never clear the setting. SettingsPatch keeps "" and a SQLAlchemy @validates on Settings.accounting_mailbox stores it as NULL. Audit before/after stays correct.
- Access-denied errors raise the same last_send_error whether the sender is accounting or support. The text names the 'Accounting mailbox' or 'Scope the app to the one mailbox' section of docs/MAIL_SETUP.md.
- Every final send failure, not only access-denied, now sets last_send_error and last_send_error_at. This includes the no-recipients case.

## Issues Encountered
(none)

## Escalations
(none)

## Handoff Context
- **Key outputs**: backend/alembic/versions/0042_accounting_mailbox.py; backend/app/mail/graph.py; backend/app/mail/ingest.py; backend/app/models.py; backend/app/notices.py; backend/app/routers/config.py; backend/app/schemas.py; backend/tests/mailfakes.py; backend/tests/test_graph_client.py; backend/tests/test_mail_ingest.py; backend/tests/test_notices.py; backend/tests/test_seed_and_migrations.py; docs/api/openapi.json
- **Decisions made**: config_services.update_settings is not in my file list and skips None values, so an "empty string becomes None" validator could never clear the setting. SettingsPatch keeps "" and a SQLAlchemy @validates on Settings.accounting_mailbox stores it as NULL. Audit before/after stays correct.; Access-denied errors raise the same last_send_error whether the sender is accounting or support. The text names the 'Accounting mailbox' or 'Scope the app to the one mailbox' section of docs/MAIL_SETUP.md.; Every final send failure, not only access-denied, now sets last_send_error and last_send_error_at. This includes the no-recipients case.
- **Open questions**: (none)
- **Conventions established**: docs/MAIL_SETUP.md needs an 'Accounting mailbox' section, because the error text refers to it. It showed as modified in git; I did not touch it, so it is presumably 18-02's.; Mail sent from the accounting mailbox has no Message-ID (internet_message_id is NULL), so customer replies are not thread-matched. Billing notices only.; New /mail/status fields for the frontend: accounting_mailbox, last_send_error, last_send_error_at.

## Requirements Covered
- R18-1
- R18-2

## Token Usage
16 requests, 954607 input tokens (886380 cached), 13599 output tokens, $0.4838
