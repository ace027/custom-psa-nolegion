# Backlog

Ideas that are not in scope for the current phase. Nothing here gets built without approval.

- Client portal (separate auth, org-scoped principal)
- Asset inventory
- Project/task boards
- Reporting
- Quotes
- Integrations: NinjaOne, Hudu, Microsoft 365 sync, n8n webhooks
- Security features: compliance evidence tracking, vCISO reporting
- Attachment malware scanning
- Entra group to role mapping
- Proration of mid-period quantity changes
- Automatic "we got your ticket" acknowledgement email (needs careful loop protection)
- Holiday calendar for SLA business hours
- Multiple business-hours calendars (per client or per priority)
- Editable ticket status labels / custom workflows
- Ticket merge, split, and linking related tickets
- Ticket templates and canned responses
- Rendering (sanitized) HTML email bodies and inline images
- Poison-message quarantine for unreadable inbound mail (currently retried every cycle)
- Multiple inbound mailboxes mapped to queues
- Time entry start/stop timers
- Delta-query mail sync (current design: poll unread in Inbox)
- Notifications (email/Teams) for new, unassigned or SLA-breached tickets
- **Payment tracking**: record payments, paid/unpaid/overdue status, A/R aging (no integrations, just tracking)
- Emailing invoices/statements from the PSA (with the PDF attached)
- Credit memos as a first-class document (currently: negative manual lines)
- Proration of mid-month agreement start/end and quantity changes
- Sales tax by jurisdiction / multiple tax rates per client
- Late fees and payment-reminder schedule
- Configurable invoice number format; invoice PDF branding/logo
- Per-user / per-device quantities populated from Microsoft 365 / NinjaOne (the Phase 3 quantity field is the hook)
- Billing reports: revenue by client, margin on products, unbilled time, agreement MRR trend
- CSV export of invoices for your accountant
- Minimum billable time per entry; retainer / block-hours agreements
