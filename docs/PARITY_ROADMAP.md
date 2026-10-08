# Roadmap to replace Autotask, HaloPSA or ConnectWise Manage

Status: **proposal, not approved.** Nothing here is built. It lists what a small MSP/MSSP usually
loses when leaving those products, ordered by how much day-to-day pain the gap causes. Each phase
follows the working agreement: plan, build with tests, update docs, seed data, manual checklist,
stop for your review.

Honest scope note: these products took hundreds of engineer-years. "Fully replace" for a 1-10 tech
MSP is realistic; "match every feature" is not and should not be the target. Anything marked
**(decide)** needs your call before building because it is hard to change later.

## 1. What already exists (from this repo)
Tickets with queues, categories, priorities, SLA clocks and business hours; email-to-ticket and
replies via Microsoft Graph; time entries (billable rounding, void-not-delete); clients, sites,
contacts; agreements, products, monthly billing runs, immutable invoices and PDFs, payments, A/R,
statements and reminders, invoice emails; revenue and unbilled reports; client portal (tickets,
invoices, statement, devices/warranty); quoting from onsite surveys; NinjaOne/Hudu asset and
warranty sync; staff notifications; audit log; roles and forced row-level security; light/dark UI.

## 2. Gaps, grouped
| Area | What commercial PSAs have that this does not |
|---|---|
| **Ticket depth** | Canned responses/templates, merge/split/link tickets, custom ticket types and fields, editable statuses/workflows, ticket-level checklists, holiday calendars, multiple SLA calendars, auto-acknowledgement email, escalation rules, CSAT surveys, recurring/scheduled tickets |
| **Scheduling and dispatch** | Technician calendar, drag-drop dispatch board, appointments, availability/PTO, on-call rotation, calendar sync (Outlook) |
| **Automation** | Rules engine (if X then assign/notify/escalate/create task), webhooks, public API keys, n8n/Teams hooks |
| **Monitoring intake** | RMM alerts (NinjaOne) to tickets with de-duplication and auto-close, device linked to ticket |
| **Projects** | Projects, phases/tasks, dependencies, budgets, project billing (fixed fee, milestones, T&M), Gantt/board views |
| **CRM / sales** | Leads, opportunities, pipeline and forecasting, quote-to-agreement (partly done), renewals |
| **Contracts and billing depth** | Block-hour/retainer agreements, proration, per-device counts from RMM, credit memos, refunds, late fees, multiple tax rates, billing approval workflow, rate cards by contract, recurring non-service charges, expense billing |
| **Procurement and inventory** | Vendors, purchase orders, receiving, serialised inventory, markup rules, drop-ship, quote-to-PO |
| **Time and expenses** | Timers, weekly timesheets with approval, expense entries and receipts, mileage, payroll/export |
| **Reporting** | Report builder or a deeper pack: SLA performance, tech utilisation, ticket aging, profitability per client/agreement, scheduled report emails, dashboards per role |
| **Knowledge and docs** | Knowledge base (internal and client-facing), suggested articles, runbooks (today: Hudu stays the system of record) |
| **Client experience** | Portal SSO, attachments, online payment (ACH/card), contact self-service, project and quote views, CSAT |
| **Staff experience** | Mobile-friendly tech view (partly), global search, saved views, bulk actions, keyboard shortcuts, notifications centre |
| **Security / compliance (your edge)** | vCISO Phases 2-5 (vulnerabilities, scorecards, PTA reports, risk register), change management, evidence tracking, CMMC-oriented audit exports |
| **Ops and trust** | Data export/import (CSV) for migration, backups UI, attachment malware scan, per-field audit, GDPR-style data removal |

## 3. Proposed phases (each ends with working, tested software)
Order is a recommendation. Reorder freely; dependencies are noted.

1. **Daily-driver tickets.** Canned responses, merge/link, custom types and fields, editable
   statuses **(decide: how flexible)**, holiday calendar, auto-acknowledgement with loop protection,
   escalation rules, CSAT, bulk actions, global search. *Biggest daily impact; no dependencies.*
2. **Time, expenses, timesheets.** Start/stop timers, weekly timesheet with approval, expenses with
   receipts and billing to invoices, export for payroll. *Feeds billing accuracy.*
3. **Contract and billing depth.** Block-hour/retainer agreements, proration, credit memos,
   refunds, late fees, multiple tax rates, per-device counts from NinjaOne **(decide: money rules
   written down and approved before code)**. *Touches billing math; highest regret risk.*
4. **Scheduling and dispatch.** Calendar, appointments tied to tickets, availability, on-call,
   Outlook calendar sync.
5. **RMM alerts to tickets.** NinjaOne alert intake, dedupe, auto-resolve, device link.
   *Reuses the Phase 1 integration framework.*
6. **Automation and API.** Rules engine, webhooks, API keys, Teams/n8n. *Do after 1 and 5 so rules
   have real events to act on.*
7. **Projects.** Projects, tasks, budgets, project billing.
8. **CRM and renewals.** Leads, opportunities, pipeline, renewal reminders, quote-to-agreement
   (extends the quoting tool).
9. **Procurement and inventory.** Vendors, POs, receiving, inventory, markup.
10. **Reporting and dashboards.** SLA, utilisation, aging, profitability, scheduled emails.
11. **Knowledge base.** Internal and client-facing articles, suggestions on tickets.
12. **vCISO Phases 2-5.** Blocked on ConnectSecure and Compliance Scorecard details.
13. **Portal and migration polish.** SSO, attachments, online payments (no processor
    integration unless you approve it), CSV import/export for moving off your current tool.

## 4. Decisions needed before building
1. **Which phase first?** Recommendation: 1, then 2, then 3.
2. **Who uses it today and what are you leaving?** Which of Autotask/Halo/ConnectWise do you use now,
   and do you need to import its data (clients, contacts, tickets, agreements)? That decides whether
   phase 13's import work moves to the front.
3. **Must-haves vs nice-to-haves.** Mark anything above you do not need; each removal saves a phase.
4. **Payments.** Online card/ACH needs a payment processor, which contradicts the earlier "no
   payment-processor integrations" rule. Keep the rule or relax it for portal payments only?
5. **Scale.** Number of techs and clients, so performance and permission design match reality.
