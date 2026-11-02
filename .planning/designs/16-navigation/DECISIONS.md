# Phase 16 navigation: owner decisions (2026-11-02)

Mockups and comparison: README.md, mockup-a.html, mockup-b.html, mockup-c.html in this folder.

| # | Question | Decision |
|---|----------|----------|
| 1 | Direction | **Mockup A (grouped, collapsible sidebar) plus the command palette from C** (Ctrl/Cmd+K: pages, tabs, ticket-number jump, quick actions). No pins for now. |
| 2 | Should techs and read-only users see Finance (Billing, Procurement)? | **No.** Not in their navigation, and not reachable by URL or API beyond what their ticket work needs (the plan must list exactly which billing/procurement reads a tech still needs on tickets, e.g. product charges on a ticket, and keep only those). |
| 3 | Service-manager role? | **Yes.** Add a "manager" role: dispatch, reports, SLA, time-off/timesheet approval and service settings; no billing finalisation, no admin (users, integrations, API keys, security settings). |
| 4 | Users page | **Admin only** (moves under Admin). |
| 5 | Split Settings | **Yes.** Settings becomes sub-pages under Admin (for example Mail and calendar, Tickets, Billing, Portal, Sales, Scheduling); existing settings keep their values and API. |
| 6 | Labels | Assumed default (not answered): keep "Organizations" and "Sales". |
| 7 | Where to remember open/closed sections | Assumed default (not answered): per browser (localStorage). |
| 8 | Billing reports location | Assumed default (not answered): stay under Billing, with a link from Reports. |

Also decided 2026-11-02: the built-in knowledge base is removed and replaced by Hudu article suggestions on tickets, so the new navigation has no Knowledge base entry.

## Permission details (owner answers, 2026-11-02)
- `billing:read` is split. `billing:read` keeps the catalog: products, rates, agreements and ticket charges (techs need them for parts and quotes). A new `invoice:read` covers invoices, invoice runs, payments, statements, reminders/notices, credit memos, write-offs, late fees and receivables.
- Techs and read-only lose `invoice:read` and all procurement (`procurement:read`, `procurement:write`); purchasing, receiving and delivery are billing/admin work, and the client page's Inventory card is hidden from them.
- New role `manager`: everything a tech has (minus procurement) plus timesheet and time-off approval, reports including profitability and aging (`report:read`), the audit log (`audit:read`), read-only invoices (`invoice:read`), and service settings through a new `service:configure` permission (queues, categories, priorities, statuses, work types, SLA, holidays). No billing write/finalize, payments, user management, integrations, API keys, automation, portal management or the general settings (`config:manage`: mail, billing, portal, security).
- The Users page is admin-only in the navigation; `user:read` stays for every role because assignee and technician pickers need it.
