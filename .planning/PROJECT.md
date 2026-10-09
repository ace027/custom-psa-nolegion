# custom-psa

## What This Is
A self-hosted professional services automation (PSA) system for a small MSP/MSSP, built to replace Autotask, HaloPSA or ConnectWise Manage. It already covers ticketing with SLAs and email intake, time and expenses, billing (agreements, invoices, payments, proration, credit memos, late fees), quoting, a client portal, NinjaOne/Hudu asset sync and an audit log. This project carries the remaining parity roadmap (docs/PARITY_ROADMAP.md) to completion.

## Core Value
One secure, self-hosted system of record for an MSP's service delivery and billing, with forced row-level security and audited writes, at parity with commercial PSAs for what a small MSP actually uses.

## Who It's For
Staff of a 1-10 technician MSP (admins, technicians, billing, read-only) and the MSP's client contacts through the client portal.

## Requirements

### Validated
(None yet — ship to validate)

### Active
- REQ-01: Block-hour / retainer agreements: prepaid hours drawn down by billable time, unused hours expire at month end (no rollover), money rules written and approved before code.
- REQ-02: Scheduling foundation: per-tech IANA timezone, weekly working hours, PTO, ticket-linked appointments (org-scoped with RLS), pure availability math, API and scheduling permissions.
- REQ-03: Dispatch board: per-tech day/week board with drag, resize and reassign using an MIT-licensed library, conflict warnings (hours, PTO, overlap), appointment shown on its ticket, start the existing timer from an appointment.
- REQ-04: Outlook one-way push: worker-only idempotent outbox pushing appointments to each tech's Outlook calendar, getSchedule free/busy cache shown on the board, failed-sync visibility; the API never calls Graph.
- REQ-05: Client confirmations and on-call: confirmation/reschedule emails to the client contact, portal appointments view, on-call rotations with overrides and a who's-on-call display.
- REQ-06: RMM alerts to tickets: NinjaOne alert intake with deduplication, auto-resolve and device link.
- REQ-07: Automation and API: rules engine (if X then assign/notify/escalate/create), outbound webhooks, API keys, Teams/n8n hooks.
- REQ-08: Projects: projects, phases/tasks, dependencies, budgets, project billing (fixed fee, milestones, T&M), board view.
- REQ-09: CRM and renewals: leads, opportunities, pipeline and forecasting, renewal reminders, quote-to-agreement.
- REQ-10: Procurement and inventory: vendors, purchase orders, receiving, serialised inventory, markup rules.
- REQ-11: Reporting and dashboards: SLA performance, tech utilisation, ticket aging, profitability per client/agreement, scheduled report emails.
- REQ-12: Knowledge base: internal and client-facing articles, article suggestions on tickets.
- REQ-13: Portal polish: Entra SSO for portal users, file attachments, contact self-service, CSV data export.

### Out of Scope
- Online card/ACH payments or any payment-processor integration (payments stay recorded by hand)
- Multiple tax rates per client (one rate per client stays until a real case appears)
- Data import from Autotask/HaloPSA/ConnectWise
- vCISO phases 2-5 (blocked on ConnectSecure and Compliance Scorecard details)
- Outlook inbound sync, Graph change notifications/webhooks, recurring appointments
- Paid calendar libraries (e.g. FullCalendar Premium)

## Constraints
- Stack is fixed: FastAPI + SQLAlchemy + Alembic + PostgreSQL backend, React 19 + Vite + Tailwind 4 + react-query frontend, Docker Compose with Caddy, a separate worker process
- Forced row-level security: API runs as psa_app (no BYPASSRLS); client-owned tables need organization_id, an RLS policy and an isolation test
- Every write goes through services.py with audit.record; client-owned queries through repositories.py with a Scope; every route has a permission, summary, tag and test (test_zz_api_contract.py)
- Applied Alembic revisions are never edited; schema changes add a new revision
- Money in USD integer cents; billing math, auth/permissions, RLS/migrations, quoting rules and security review stay on the main model (CLAUDE.md)
- Only the worker holds the Microsoft Graph secret; Graph is app-only and scoped with Exchange RBAC for Applications
- Tests run against real PostgreSQL (never SQLite); each phase ends with working, tested software, docs, seed data and a manual checklist (docs/verify/)
- MIT/free libraries only unless the owner approves otherwise

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Block-hour unused hours expire at month end (no rollover) | Recorded in docs/BILLING_PLAN.md; simplest money rule. | Pending |
| Keep one tax rate per client | Options 2/3 change invoice layout and reports; revisit only when a real case appears (BILLING_PLAN option E). | Pending |
| No payment processor; portal payments stay manual | Keeps the existing no-processor rule and avoids PCI scope. | Pending |
| No data import from another PSA | Owner does not need to migrate data; CSV export stays in portal polish. | Pending |
| Scheduling follows approach B from .planning/explorations/2026-10-09-scheduling-dispatch-design.md | PSA is the source of truth with one-way worker push to Outlook and a free/busy cache; keeps the worker-only Graph boundary and reuses the outbox/retry pattern. | Pending |
| Scheduling supports per-tech timezones | Owner chose per-tech timezone over a single org timezone. | Pending |
| Calendar board uses an MIT library (react-big-calendar after a spike) | Owner chose free/MIT only; FullCalendar resource views are paid. | Pending |
| Appointments link to tickets only (no SLA or billing effect) | Owner chose link-only integration; can start the existing timer. | Pending |

## Architecture Influences
Layered FastAPI app: routers -> services.py (business rules, audit) -> repositories.py (Scope-filtered queries) over PostgreSQL with forced RLS. A worker process (app.worker) runs mail, billing, notification and integration jobs and alone talks to Microsoft Graph. React SPA with staff app, client portal and public CSAT shells, gated by permissions. Caddy serves the frontend and proxies /api. See .planning/CODEBASE.md.

---
*Last updated: 2026-10-09 after initialization*
