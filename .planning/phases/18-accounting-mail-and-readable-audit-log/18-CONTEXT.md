# Phase 18: Accounting mail and readable audit log -- Context

## Phase Goal
Statements and payment reminders come from the accounting mailbox, and the audit log reads like plain English.

## Requirements Covered
- R18-1 (owner note 2): Settings has an accounting sender address in the same M365 tenant; statements, reminders and invoice emails are sent from it, everything else from the support mailbox
- R18-2 (owner note 2): docs/MAIL_SETUP.md covers adding the accounting mailbox to the app's access scope; a missing permission shows a clear error
- R18-3 (owner note 9): each audit entry shows a one-line human sentence (who did what to which record), field-level before/after as readable changes, raw JSON on demand
- R18-4 (owner note 9): the audit log can be filtered by person, record type and date

## What Already Exists (from prior phases)
- Outbound mail: EmailMessage rows (direction out, send_status pending) are sent by app/mail/ingest.py send_pending via GraphClient.send_mail (app/mail/graph.py, draft + send so internetMessageId is ours); the mailbox is env MAIL_MAILBOX; GraphClient._request_user(user, ...) already exists; tests use backend/tests/mailfakes.py
- All billing notices (kind statement, reminder, invoice) are sent through one funnel: app/notices.py send_notice (EmailMessage created around line 806)
- GraphError carries a public message; send_pending stores str(exc) in send_error, retries up to MAX_SEND_ATTEMPTS=5 then audits email.send_failed; send_error is shown nowhere in the UI
- MailboxStatus (models.py:595) has last_error/last_error_at for polling; GET /mail/status (routers/config.py, config:manage) returns MailStatusOut; frontend/src/pages/admin/settings/MailCalendarSettings.tsx shows a read-only connector card
- Settings single row (models.py:277), SettingsOut/SettingsPatch in schemas.py, PATCH /settings needs config:manage and audits settings.update
- AuditLog model (models.py:178), audit.record in app/audit.py, GET /audit in routers/users.py (audit:read) with filters entity_type, entity_id, organization_id, actor_id, action prefix; repo.list_audit in repositories.py:91; AuditOut in schemas.py:229; frontend/src/pages/Audit.tsx is a 48-line raw table
- report_metrics.py has _zone(user_tz, settings_tz) and _bounds(start, end, tz) for local-day bounds
- Alembic head is 0041; head assertion in backend/tests/test_seed_and_migrations.py:49

## Key Design Decisions
- ASSUMED: the accounting sender applies to every notice sent by notices.send_notice (statements, payment reminders and invoice emails, all accounting mail); ticket mail, auto-acks, CSAT, appointment, quote, renewal and report mail stay on the support mailbox
- ASSUMED: new nullable column settings.accounting_mailbox (String 320); empty means everything goes from the support mailbox, so nothing changes until the owner sets it
- The sender is recorded per message at creation: send_notice sets EmailMessage.from_email to the accounting mailbox; send_pending sends from e.from_email when it is set and differs from the support mailbox, otherwise from the support mailbox, and after a send from_email is the mailbox actually used
- Least privilege: mail from the accounting mailbox uses Graph POST /users/{accounting}/sendMail (Mail.Send only, saveToSentItems true), so the app never needs read access to the accounting mailbox; such messages store internet_message_id NULL (replies to accounting mail are not ticketed, which is intended)
- A 403 / ErrorAccessDenied / ErrorSendAsDenied / 404 ErrorInvalidUser / MailboxNotEnabledForRESTAPI on a send is a permanent failure: the message is marked failed at once (no retry) with a plain error naming the mailbox and docs/MAIL_SETUP.md section 'Accounting mailbox', audited as email.send_failed, and recorded in new mailbox_status.last_send_error / last_send_error_at, shown on the Mail & calendar settings page
- Migration 0042 adds settings.accounting_mailbox and mailbox_status.last_send_error, last_send_error_at
- Audit text is computed server-side in a new pure module app/audit_text.py and returned as new AuditOut fields actor_name, organization_name, summary, changes; the raw before/after/detail stay in the response for the 'Show raw' toggle
- Audit date filters date_from/date_to are inclusive local dates in the company timezone (Settings timezone via report_metrics._zone/_bounds); a GET /audit/entity-types endpoint feeds the record-type filter; the person filter uses the users list the frontend already loads
- Audit stays audit:read only; no new permissions

## Plan Structure
- **Plan 18-01 (Wave 1)**: Accounting sender mailbox: setting, sending and clear errors -- Add the accounting sender setting, send billing notices from it with Mail.Send-only Graph sendMail, and turn a missing mailbox permission into an immediate, plain, visible error.
- **Plan 18-02 (Wave 1)**: MAIL_SETUP: accounting mailbox scope -- Document how to add the accounting mailbox to the mail app's Exchange RBAC scope with Mail.Send only, how to verify it, and what the error looks like when it is missing.
- **Plan 18-03 (Wave 2)**: Readable audit entries and filters (backend) -- Return a plain-English sentence, readable field changes, the actor and client names for every audit entry, and add date and record-type filters.
- **Plan 18-04 (Wave 3)**: Readable audit page and accounting sender in settings (frontend) -- Show each audit entry as a sentence with readable changes and a raw-JSON toggle, add person/record-type/date filters, and let admins set the accounting sender and see the last send error.
