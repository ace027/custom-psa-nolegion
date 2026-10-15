# Phase 5: Client confirmations + on-call -- Context

## Phase Goal
Clients get an email when an appointment on their ticket is booked, moved or cancelled, and can see upcoming appointments in the portal; staff can set up weekly on-call rotations with overrides and see who is on call now, in the sidebar and on the dispatch board.

## Requirements Covered
- REQ-05: client confirmations for appointments (booked/moved/cancelled) and on-call rotations

## What Already Exists (from prior phases)
- Phase 3: appointments (models.py Appointment: status scheduled|cancelled, client_visible, notes, cancel_reason), scheduling.create_appointment/update_appointment/cancel_appointment, dispatch board (scheduling/board.ts backgroundBlocks, Dispatch.tsx), schedule:read / schedule:write / timeoff:approve permissions (admin+tech write; billing/read_only read)
- Phase 4: Outlook push via calendar outbox in worker; busy blocks drawn on the board as outlook_busy background kind; latest migration 0025
- Email outbox: email_messages (direction out, send_status pending, ticket_id) drained by mail/ingest.py send_pending in the worker run_cycle; notices.send_notice queues rows; audit.record for audit trail
- Portal: routers/portal.py + app/portal.py with _visible ticket rule, portal_deps.PortalCtx scoped to the contact's org; frontend/src/portal/PortalApp.tsx
- Settings row (models.py Settings, schemas.py SettingsOut/SettingsPatch, pages/Settings.tsx)
- Forced RLS pattern: ENABLE+FORCE, policy org_scope using app_org_visible(organization_id), grants to psa_app, sequence usage grant

## Key Design Decisions
- Client email is notify-only to the ticket's contact (Contact.email), falling back to Ticket.requester_email; no reply handling, no confirm/decline links
- Settings.appointment_emails_enabled (default false) is the master switch; per-appointment notify_client (default true) is a 'Don't email client' box in the booking and edit dialogs
- Emails only for client_visible appointments; internal notes are never included
- Debounce: changes upsert one pending appointment_notices row per appointment with send_after = now + 2 minutes; the worker derives the kind at send time (booked / moved / cancelled / skip) by comparing with the last sent snapshot, so a book-then-move within 2 minutes sends one 'booked' email with the final time and a book-then-cancel sends nothing
- A reassignment with no time change sends nothing; a time change is a move
- Email templates are fixed plain text in code, times shown in the business timezone, tech shown by first name only
- On-call is display only: no alerts, paging or SLA escalation
- Rotations are weekly with an ordered member list, a handoff weekday and time in the business timezone, an anchor_date on the handoff weekday, and dated overrides (latest created override wins); managed with schedule:write, read with schedule:read
- Portal shows client_visible scheduled appointments from 30 days ago onward, only for tickets the contact may already see
- Owner preference PRF-001: no owner manual testing until Phase 14: Verify; this phase writes docs/verify/client-notices-oncall.md and appends its checks to .planning/VERIFY.md
- Retro constraints: build with --single-wave; the schema plan grants every privilege later waves need and tests them with has_table_privilege; a build commit holding only SUMMARY.md fails the plan; escalation types are architecture, dependency, scope, schema, api, deletion, infrastructure, quality

## Plan Structure
- **Plan 05-01 (Wave 1)**: Schema, models, schemas and on-call math -- Add migration 0026 with the notice queue and on-call tables, the ORM models, every Pydantic schema later plans need, and a pure on-call calculator.
- **Plan 05-02 (Wave 2)**: Client appointment emails -- Queue a debounced notice on every client-visible appointment change and have the worker turn due notices into outbound emails to the ticket contact.
- **Plan 05-03 (Wave 2)**: On-call API and portal appointments -- Expose on-call rotation management and who-is-on queries to staff, and upcoming appointments to portal contacts.
- **Plan 05-04 (Wave 3)**: Staff UI: email switch, on-call page, widget and board -- Let staff turn appointment emails on, opt a booking out, see notice state, manage rotations, and see who is on call in the sidebar and on the dispatch board.
- **Plan 05-05 (Wave 3)**: Portal appointments page, docs and verify checklist -- Show upcoming appointments in the client portal and document the phase, including the deferred owner checks.
