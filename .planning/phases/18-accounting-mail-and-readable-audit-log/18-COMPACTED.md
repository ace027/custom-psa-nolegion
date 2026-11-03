---
phase: 18-accounting-mail-and-readable-audit-log
compacted: 2026-11-03
original_summaries: [18-01-SUMMARY.md, 18-02-SUMMARY.md, 18-03-SUMMARY.md, 18-04-SUMMARY.md]
requirements_satisfied: [R18-1, R18-2, R18-3, R18-4]
---

# Phase 18: Accounting mail and readable audit log — Compacted Summary

## Deliverables
- 18-01 Accounting sender mailbox: setting, sending and clear errors (Complete): backend/alembic/versions/0042_accounting_mailbox.py, backend/app/mail/graph.py, backend/app/mail/ingest.py, backend/app/models.py, backend/app/notices.py, backend/app/routers/config.py, backend/app/schemas.py, backend/tests/mailfakes.py, backend/tests/test_graph_client.py, backend/tests/test_mail_ingest.py, backend/tests/test_notices.py, backend/tests/test_seed_and_migrations.py, docs/api/openapi.json
- 18-02 MAIL_SETUP: accounting mailbox scope (Complete): docs/MAIL_SETUP.md
- 18-03 Readable audit entries and filters (backend) (Complete): backend/app/audit_text.py, backend/app/repositories.py, backend/app/routers/users.py, backend/app/schemas.py, backend/tests/test_audit.py, backend/tests/test_audit_text.py, docs/api/openapi.json
- 18-04 Readable audit page and accounting sender in settings (frontend) (Complete): frontend/src/api.ts, frontend/src/pages/Audit.test.tsx, frontend/src/pages/Audit.tsx, frontend/src/pages/admin/settings/MailCalendarSettings.test.tsx, frontend/src/pages/admin/settings/MailCalendarSettings.tsx

## Decisions
- 18-01: config_services.update_settings is not in my file list and skips None values, so an "empty string becomes None" validator could never clear the setting. Setting
- 18-01: Access-denied errors raise the same last_send_error whether the sender is accounting or support. The text names the 'Accounting mailbox' or 'Scope the app to th
- 18-01: Every final send failure, not only access-denied, now sets last_send_error and last_send_error_at. This includes the no-recipients case.
- 18-02: The section heading is unnumbered, as the plan specifies, so existing numbering is unchanged.
- 18-02: The Troubleshooting row and the pointer sentence both link to the `#accounting-mailbox` anchor.
- 18-03: The new `AuditOut` fields have defaults, and the route fills them after `model_validate`.
- 18-03: Date bounds use the business timezone from settings, through `report_metrics._zone` and `_bounds`.
- 18-03: `actor_name` is looked up only for `actor_type == "user"`. A deleted or unknown user shows as `User #N`.
- 18-04: The accounting field lives inside the existing "Mailbox connector" card, not a new card. src/SettingsSplit.test.tsx (outside my file list) asserts the exact car
- 18-04: The Person filter reuses the ["users"] query and the /users call that other pages use.
- 18-04: The accounting field only renders for users with config:manage.

## Conventions and Open Questions
- 18-01 convention: docs/MAIL_SETUP.md needs an 'Accounting mailbox' section, because the error text refers to it. It showed as modified in git
- 18-01 convention: I did not touch it, so it is presumably 18-02's.
- 18-01 convention: Mail sent from the accounting mailbox has no Message-ID (internet_message_id is NULL), so customer replies are not thread-matched. Billing notices only.
- 18-02 convention: The doc's error text is "The mail app is not allowed to send as accounting@…". 18-01's runtime error should contain the phrase "not allowed to send as" and name
- 18-02 convention: The doc says the setting is at Settings → Mail & calendar → "Accounting sender address". 18-04's frontend label should match that.
- 18-03 convention: The frontend can use `summary`, `actor_name`, `organization_name` and `changes[{field,label,before,after}]`.
- 18-03 convention: It can also use the `date_from` and `date_to` query params and the `/audit/entity-types` list for the record-type dropdown. Both are inclusive local dates.
- 18-04 convention: The audit query string uses the params actor_id, entity_type, date_from, date_to and action, and omits empty ones.
- 18-04 convention: If the entity-types request fails, the Record type select keeps only "Any" and shows the error.

## Files Modified
| File | Change |
|------|--------|
| `backend/alembic/versions/0042_accounting_mailbox.py` | 18-01: Accounting sender mailbox: setting, sending and clear errors |
| `backend/app/mail/graph.py` | 18-01: Accounting sender mailbox: setting, sending and clear errors |
| `backend/app/mail/ingest.py` | 18-01: Accounting sender mailbox: setting, sending and clear errors |
| `backend/app/models.py` | 18-01: Accounting sender mailbox: setting, sending and clear errors |
| `backend/app/notices.py` | 18-01: Accounting sender mailbox: setting, sending and clear errors |
| `backend/app/routers/config.py` | 18-01: Accounting sender mailbox: setting, sending and clear errors |
| `backend/app/schemas.py` | 18-01: Accounting sender mailbox: setting, sending and clear errors |
| `backend/tests/mailfakes.py` | 18-01: Accounting sender mailbox: setting, sending and clear errors |
| `backend/tests/test_graph_client.py` | 18-01: Accounting sender mailbox: setting, sending and clear errors |
| `backend/tests/test_mail_ingest.py` | 18-01: Accounting sender mailbox: setting, sending and clear errors |
| `backend/tests/test_notices.py` | 18-01: Accounting sender mailbox: setting, sending and clear errors |
| `backend/tests/test_seed_and_migrations.py` | 18-01: Accounting sender mailbox: setting, sending and clear errors |
| `docs/api/openapi.json` | 18-01: Accounting sender mailbox: setting, sending and clear errors |
| `docs/MAIL_SETUP.md` | 18-02: MAIL_SETUP: accounting mailbox scope |
| `backend/app/audit_text.py` | 18-03: Readable audit entries and filters (backend) |
| `backend/app/repositories.py` | 18-03: Readable audit entries and filters (backend) |
| `backend/app/routers/users.py` | 18-03: Readable audit entries and filters (backend) |
| `backend/app/schemas.py` | 18-03: Readable audit entries and filters (backend) |
| `backend/tests/test_audit.py` | 18-03: Readable audit entries and filters (backend) |
| `backend/tests/test_audit_text.py` | 18-03: Readable audit entries and filters (backend) |
| `docs/api/openapi.json` | 18-03: Readable audit entries and filters (backend) |
| `frontend/src/api.ts` | 18-04: Readable audit page and accounting sender in settings (frontend) |
| `frontend/src/pages/Audit.test.tsx` | 18-04: Readable audit page and accounting sender in settings (frontend) |
| `frontend/src/pages/Audit.tsx` | 18-04: Readable audit page and accounting sender in settings (frontend) |
| `frontend/src/pages/admin/settings/MailCalendarSettings.test.tsx` | 18-04: Readable audit page and accounting sender in settings (frontend) |
| `frontend/src/pages/admin/settings/MailCalendarSettings.tsx` | 18-04: Readable audit page and accounting sender in settings (frontend) |

## Verification
- 18-01 (R18-1, R18-2): 7/7 verification commands passed
- 18-02 (R18-2): 4/4 verification commands passed
- 18-03 (R18-3, R18-4): 6/6 verification commands passed
- 18-04 (R18-1, R18-2, R18-3, R18-4): 5/5 verification commands passed

## Agents
- 18-01: engineering-backend-architect
- 18-02: product-technical-writer
- 18-03: engineering-backend-architect
- 18-04: engineering-frontend-developer
