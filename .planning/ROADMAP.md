# custom-psa — Roadmap

## Phases

- [x] Phase 1: Block-hour / retainer agreements (3 plans)
- [ ] Phase 2: Scheduling: availability & appointments (3 plans)
- [ ] Phase 3: Dispatch board (3 plans)
- [ ] Phase 4: Outlook push + free/busy (3 plans)
- [ ] Phase 5: Client confirmations + on-call (3 plans)
- [ ] Phase 6: RMM alerts to tickets (3 plans)
- [ ] Phase 7: Automation & API (4 plans)
- [ ] Phase 8: Projects & project billing (4 plans)
- [ ] Phase 9: CRM & renewals (3 plans)
- [ ] Phase 10: Procurement & inventory (3 plans)
- [ ] Phase 11: Reporting & dashboards (3 plans)
- [ ] Phase 12: Knowledge base (2 plans)
- [ ] Phase 13: Portal polish (3 plans)

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
- [ ] Owner approves RBAC-scoped Calendars.ReadWrite; spike verified on a real tenant
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

### Phase 12: Knowledge base
**Goal**: Staff and clients find answers in internal and client-facing articles, suggested on tickets.
**Requirements**: REQ-12
**Recommended Agents**: engineering-backend-architect, support-support-responder
**Success Criteria**:
- [ ] Articles with internal/client visibility (portal sees only client-facing)
- [ ] Search and suggestions on the ticket page
**Plans**: 2

### Phase 13: Portal polish
**Goal**: Client users sign in with Entra SSO, attach files, manage their contact details and export their data.
**Requirements**: REQ-13
**Recommended Agents**: engineering-security-engineer, engineering-frontend-developer
**Success Criteria**:
- [ ] Entra SSO for portal users alongside one-time links, security reviewed
- [ ] Attachments on portal tickets
- [ ] Contact self-service and CSV export, isolation tested
**Plans**: 3

## Progress

| Phase | Plans | Completed | Status |
|-------|-------|-----------|--------|
| 1 | 3 | 3 | Complete |
| 2 | 3 | 2 | In Progress |
| 3 | 3 | 0 | Pending |
| 4 | 3 | 0 | Pending |
| 5 | 3 | 0 | Pending |
| 6 | 3 | 0 | Pending |
| 7 | 4 | 0 | Pending |
| 8 | 4 | 0 | Pending |
| 9 | 3 | 0 | Pending |
| 10 | 3 | 0 | Pending |
| 11 | 3 | 0 | Pending |
| 12 | 2 | 0 | Pending |
| 13 | 3 | 0 | Pending |
