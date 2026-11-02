# custom-psa — Roadmap

## Phases

- [x] Phase 1: Block-hour / retainer agreements (3 plans)
- [x] Phase 2: Scheduling: availability & appointments (3 plans)
- [x] Phase 3: Dispatch board (3 plans)
- [x] Phase 4: Outlook push + free/busy (3 plans)
- [x] Phase 5: Client confirmations + on-call (3 plans)
- [x] Phase 6: RMM alerts to tickets (3 plans)
- [x] Phase 7: Automation & API (4 plans)
- [x] Phase 8: Projects & project billing (4 plans)
- [x] Phase 9: CRM & renewals (3 plans)
- [x] Phase 10: Procurement & inventory (3 plans)
- [x] Phase 11: Reporting & dashboards (3 plans)
- [x] Phase 12: Integration readiness (3 plans)
- [x] Phase 13: Knowledge base (2 plans)
- [x] Phase 14: Portal polish (3 plans)
- [ ] Phase 15: Verify (owner manual testing) (1 plan)
- [ ] Phase 16: Front-end redesign (navigation and layout)
- [ ] Phase 17: Agreement billing and profitability
- [ ] Phase 18: Accounting mail and readable audit log
- [ ] Phase 19: Azure deployment and onboarding wizard

## Phase Details

### Phase 1: Block-hour / retainer agreements
**Goal**: Agreements can carry prepaid block hours that billable time draws down, with unused hours expiring at month end and overage billed per the approved money rules.
**Requirements**: REQ-01
**Recommended Agents**: engineering-senior-developer, engineering-backend-architect
**Success Criteria**:
- [ ] Money rules for block hours written and approved before code
- [ ] Billing run draws down block hours and bills overage correctly, tested with exact cents
- [ ] Unused hours expire at month end with no rollover
- [ ] Docs, seed data and docs/verify checklist updated
**Plans**: 3

### Phase 2: Scheduling: availability & appointments
**Goal**: Techs have a timezone, working hours and PTO, and staff can create ticket-linked appointments with availability checks via the API.
**Requirements**: REQ-02
**Recommended Agents**: engineering-backend-architect, engineering-senior-developer
**Success Criteria**:
- [ ] New tables have organization_id/RLS where client-owned and isolation tests pass
- [ ] Availability math is pure, beside sla.py, reuses Holiday, and passes DST property tests
- [ ] Scheduling permissions added and every new route passes test_zz_api_contract
**Plans**: 3

### Phase 3: Dispatch board
**Goal**: A dispatcher books, moves and reassigns ticket appointments on a per-tech day/week drag-and-drop board.
**Requirements**: REQ-03
**Recommended Agents**: engineering-frontend-developer, engineering-senior-developer
**Success Criteria**:
- [ ] Library spike confirms MIT licence and React 19 drag-and-drop before adoption
- [ ] Board supports drag, resize and reassign with conflict warnings for hours, PTO and overlap
- [ ] Appointment shown on its ticket; timer can be started from it
- [ ] Playwright booking flow passes
**Plans**: 3

### Phase 4: Outlook push + free/busy
**Goal**: Appointments appear in each tech's Outlook calendar via a worker outbox, and Outlook busy time shows on the board.
**Requirements**: REQ-04
**Recommended Agents**: engineering-backend-architect, engineering-security-engineer, engineering-infrastructure-devops
**Success Criteria**:
- [ ] Owner approves RBAC-scoped Calendars.ReadWrite (real-tenant spike deferred to Phase 15: Verify)
- [ ] Outbox push is idempotent (create/update/delete/reassign) and tested against fake_graph
- [ ] getSchedule cache refreshes and renders on the board; failed syncs are visible
- [ ] MAIL_SETUP/calendar setup docs updated
**Plans**: 3

### Phase 5: Client confirmations + on-call
**Goal**: Clients are told when visits are booked or moved and can see them in the portal; the team has an on-call rotation.
**Requirements**: REQ-05
**Recommended Agents**: engineering-backend-architect, engineering-frontend-developer
**Success Criteria**:
- [ ] Confirmation and reschedule emails sent to the chosen contact
- [ ] Portal shows the client's appointments only (isolation tested)
- [ ] On-call rotations with overrides and a who's-on-call display
**Plans**: 3

### Phase 6: RMM alerts to tickets
**Goal**: NinjaOne alerts become deduplicated tickets linked to the device and auto-resolve when the alert clears.
**Requirements**: REQ-06
**Recommended Agents**: engineering-backend-architect, testing-api-tester
**Success Criteria**:
- [ ] Alert intake creates one ticket per open condition (dedupe tested)
- [ ] Ticket links to the synced asset
- [ ] Cleared alerts auto-resolve per a configurable rule
**Plans**: 3

### Phase 7: Automation & API
**Goal**: Admins define rules that act on ticket and alert events, and external tools integrate via webhooks and API keys.
**Requirements**: REQ-07
**Recommended Agents**: engineering-backend-architect, engineering-security-engineer
**Success Criteria**:
- [ ] Rules engine evaluates conditions and runs assign/notify/escalate/create actions with audit
- [ ] Outbound webhooks signed and retried from the worker
- [ ] API keys scoped by permission, hashed at rest, revocable
- [ ] Teams/n8n delivery works via webhooks
**Plans**: 4

### Phase 8: Projects & project billing
**Goal**: Staff run client projects with phases, tasks, dependencies and budgets, billed fixed-fee, by milestone or T&M.
**Requirements**: REQ-08
**Recommended Agents**: engineering-senior-developer, engineering-frontend-developer
**Success Criteria**:
- [ ] Projects/tasks with dependencies and a board view
- [ ] Budget vs actual from time entries
- [ ] Project billing modes produce correct invoice lines (money rules approved first)
**Plans**: 4

### Phase 9: CRM & renewals
**Goal**: Sales work is tracked from lead to agreement, with renewal reminders.
**Requirements**: REQ-09
**Recommended Agents**: engineering-backend-architect, engineering-frontend-developer
**Success Criteria**:
- [ ] Leads and opportunities with pipeline stages and a forecast view
- [ ] Accepted quote converts to an agreement
- [ ] Renewal reminders generated ahead of agreement end dates
**Plans**: 3

### Phase 10: Procurement & inventory
**Goal**: Hardware and software purchases are ordered, received, tracked in inventory and billed with markup.
**Requirements**: REQ-10
**Recommended Agents**: engineering-backend-architect, engineering-senior-developer
**Success Criteria**:
- [ ] Vendors and purchase orders with receiving
- [ ] Serialised inventory tracked to client/asset
- [ ] Markup rules feed invoice lines
**Plans**: 3

### Phase 11: Reporting & dashboards
**Goal**: Managers see SLA, utilisation, aging and profitability, and receive scheduled report emails.
**Requirements**: REQ-11
**Recommended Agents**: data-analytics-engineer, engineering-frontend-developer
**Success Criteria**:
- [ ] SLA performance, utilisation, aging and profitability reports with CSV
- [ ] Role dashboards
- [ ] Scheduled report emails sent by the worker
**Plans**: 3

### Phase 12: Integration readiness
**Goal**: Before first release, add the small forward-compatible hooks the future RMM (Rust) and vCISO modules need (stable UUIDs, external IDs, typed note authors, automation time, a versioned API with a committed OpenAPI spec, Entra tenant IDs and white-label branding), without building any integration.
**Requirements**: REQ-14
**Recommended Agents**: engineering-backend-architect, engineering-frontend-developer
**Success Criteria**:
- [ ] Organizations, sites and contacts have a backfilled, unique, NOT NULL uuid exposed in every API response; integer ids and routes unchanged
- [ ] organizations.rmm_client_id (nullable unique UUID); assets.source (manual/rmm/import) and external_id unique per (source, external_id)
- [ ] tickets.source is manual/email/portal/rmm/api/rule (ui renamed to manual) and tickets.external_ref is unique per (source, external_ref)
- [ ] ticket_notes.author_type human/system/ai (author-less notes backfilled as system), rendered distinctly and filterable on the ticket page
- [ ] time_entries.entry_type labour/automation; automation can never be billable or invoiced; reports show automation minutes separately, outside utilisation % and labour cost
- [ ] Every route under /api/v1 (no /api alias); openapi.json exported and committed, with a test that fails when it is stale
- [ ] users.entra_tenant_id stored at login beside entra_oid
- [ ] Product name, logo and colours come from one branding config; client-scoped frontend calls go through one useClientScope hook
- [ ] Migrations reversible and run cleanly on a seeded copy of current data; full suites pass
**Plans**: 3

### Phase 13: Knowledge base
**Goal**: Staff and clients find answers in internal and client-facing articles, suggested on tickets.
**Requirements**: REQ-12
**Recommended Agents**: engineering-backend-architect, support-support-responder
**Success Criteria**:
- [ ] Articles with internal/client visibility (portal sees only client-facing)
- [ ] Search and suggestions on the ticket page
**Plans**: 2

### Phase 14: Portal polish
**Goal**: Client users sign in with Entra SSO, attach files, manage their contact details and export their data.
**Requirements**: REQ-13
**Recommended Agents**: engineering-security-engineer, engineering-frontend-developer
**Success Criteria**:
- [ ] Entra SSO for portal users alongside one-time links, security reviewed
- [ ] Attachments on portal tickets
- [ ] Contact self-service and CSV export, isolation tested
**Plans**: 3

### Phase 15: Verify (owner manual testing)
**Goal**: The owner runs every manual check deferred from phases 1-14 in one pass: real-tenant and real-vendor checks, and the docs/verify/ checklists. Failures become fix tasks before release.
**Requirements**: none (verification only)
**Recommended Agents**: testing-qa-verification-specialist
**Success Criteria**:
- [ ] Every item in .planning/VERIFY.md has been run by the owner and marked pass or fail
- [ ] Each failure has a fix committed and re-checked, or an owner-accepted deferral
- [ ] Real-tenant Outlook spike (graph_calendar_spike.py, including --write and --outside) passes
**Plans**: 1

### Phase 16: Front-end redesign (navigation and layout)
**Goal**: Staff find what they need without scanning a long sidebar. The owner compares 2-3 navigation/layout mockups, picks one, and the app moves to it.
**Requirements**: owner test note 4 (too many options in the left sidebar)
**Recommended Agents**: design-ux-architect, design-ui-designer, engineering-frontend-developer
**Success Criteria**:
- [ ] 2-3 mockups of the navigation and layout reviewed by the owner, one chosen and recorded in .planning/designs/
- [ ] The sidebar is reorganised into the chosen structure; every existing page stays reachable and existing deep links keep working
- [ ] Role access follows .planning/designs/16-navigation/DECISIONS.md (finance hidden from techs and read-only, new manager role, Users admin-only), enforced by the API, not only hidden in the navigation; no page is shown to a role that cannot use it
- [ ] Keyboard and screen-reader navigation work; layout works at 1280px and on a tablet width
**Plans**: TBD

### Phase 17: Agreement billing and profitability
**Goal**: Every ticket and time entry is billed to an agreement, so utilisation and per-agreement profitability are true, including flat-fee all-you-can-eat clients.
**Requirements**: owner test note 8; P01-01 note (flat-fee AYCE: all time attaches to the flat-fee agreement, nothing extra billed, profitability tracked); block-hour rollover configurable (runbook owner decision)
**Recommended Agents**: engineering-backend-architect, support-finance-tracker, engineering-frontend-developer
**Success Criteria**:
- [ ] Tickets and time entries carry an agreement (defaulted from the client's active agreement, changeable by staff)
- [ ] Time on a flat-fee agreement is recorded and costed but never billed as extra
- [ ] Profitability and utilisation reports break down by agreement, including flat-fee agreements
- [ ] Block-hour unused-hour handling is configurable per agreement (expire at period end, or roll over with an optional cap)
**Plans**: TBD

### Phase 18: Accounting mail and readable audit log
**Goal**: Statements and payment reminders come from the accounting mailbox, and the audit log reads like plain English.
**Requirements**: owner test notes 2 and 9
**Recommended Agents**: engineering-backend-architect, engineering-frontend-developer, product-technical-writer
**Success Criteria**:
- [ ] Settings has an accounting sender address (e.g. accounting@mymsp.com, a mailbox in the same Microsoft 365 tenant); statements and reminders are sent from it, everything else from the support mailbox
- [ ] docs/MAIL_SETUP.md covers adding the accounting mailbox to the mail app's access scope; a missing permission shows a clear error
- [ ] Each audit entry shows a one-line human sentence (who did what to which record), with field-level before/after shown as readable changes; raw JSON stays available on demand
- [ ] The audit log can be filtered by person, record type and date
**Plans**: TBD

### Phase 19: Azure deployment and onboarding wizard
**Goal**: The PSA runs on Azure in Docker with its secrets in Azure Key Vault, and a first-run wizard creates and connects the SSO, Mail and Calendar app registrations.
**Requirements**: owner test note 3
**Recommended Agents**: engineering-infrastructure-devops, engineering-security-engineer, engineering-backend-architect
**Success Criteria**:
- [ ] A documented, repeatable Azure deployment (container hosting, PostgreSQL, storage for attachments) with secrets read from Key Vault, none in .env
- [ ] A first-run onboarding wizard, admin-only, that creates or connects the staff SSO, portal SSO, Mail and Calendar app registrations with least-privilege permissions, and verifies each
- [ ] Secrets created by the wizard go straight to Key Vault and are never shown again or logged
- [ ] Security review passes with no unresolved CRITICAL/HIGH findings
**Plans**: TBD

## Progress

| Phase | Plans | Completed | Status |
|-------|-------|-----------|--------|
| 1 | 3 | 3 | Complete |
| 2 | 3 | 3 | Shipped |
| 3 | 3 | 3 | Shipped |
| 4 | 4 | 4 | Shipped |
| 5 | 5 | 5 | Shipped |
| 6 | 3 | 3 | Shipped |
| 7 | 4 | 4 | Shipped |
| 8 | 4 | 4 | Shipped |
| 9 | 3 | 3 | Shipped |
| 10 | 3 | 3 | Shipped |
| 11 | 3 | 3 | Shipped |
| 12 | 4 | 4 | Shipped |
| 13 | 2 | 2 | Complete |
| 14 | 3 | 3 | Complete |
| 15 | 1 | 1 | Executed |
| 16 | 4 | 0 | Planned |
| 17 | 0 | 0 | Pending |
| 18 | 0 | 0 | Pending |
| 19 | 0 | 0 | Pending |
