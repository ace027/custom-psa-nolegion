# Parity Phase 1: daily-driver tickets (plan)

Status: **decisions made (section 5); building in slices A to D.**
Part of [PARITY_ROADMAP.md](PARITY_ROADMAP.md).

## 1. What exists today (verified in code)
- Five fixed statuses stored as a CHECK-constrained string (`new, open, waiting_on_customer, resolved, closed`); labels live only in the frontend. Behaviour hangs off them: SLA clock pauses in `waiting_on_customer/resolved/closed`, customer activity reopens, "open" filters and the dashboard use `new/open/waiting`.
- SLA targets sit on priorities; one business-hours calendar in the settings row; **no holidays**.
- Notes are immutable by DB grant (insert/select only). Internal vs customer-visible notes; customer notes can be emailed (outbox with retries). Inbound mail has loop protection and threading by `[#number]` token and headers.
- Ticket list: filters and search by subject/number, fixed 100 rows, no paging UI, no bulk actions, no sorting.
- Found while reading: outbound emails carry no threading headers (replies thread only via the subject token), and an unused "ticket_created_unmatched" counter in the ingest stats. Both get fixed in slice B.

## 2. Scope, in slices (each ends tested, documented and pushed; I stop for review after the phase)
**A. List and speed.** Real paging and sorting on the ticket list, **bulk actions** (assign, status, queue, priority, close; per-ticket audit rows; capped at 100), **canned responses** (shared templates with a few placeholders such as `{{contact_name}}`, `{{ticket_number}}`; insert into a note), and **global search** (tickets, clients, contacts, devices; respects permissions and RLS).
**B. Email and SLA correctness.** **Holiday calendar** (dates with names, optional half days) used by the SLA math; **auto-acknowledgement** email for tickets created from email, with loop protection (never to automated senders, `Auto-Submitted` header, one per sender per ticket, daily cap, on/off setting); **outbound threading headers** so replies thread properly; **escalation**: notify a configured person/mailbox when a ticket breaches SLA (and optionally bump priority, off by default).
**C. Flexibility.** **Ticket types and custom fields** (text, number, date, dropdown, checkbox; per type; shown on the ticket and in the portal only if marked client-visible) and **editable statuses** (decision below).
**D. Relationships and feedback.** **Link tickets** (related, duplicate of, parent/child) and **merge** (decision below); **CSAT**: a one-click rating link when a ticket is resolved, an optional comment, a satisfaction summary on the dashboard.

## 3. Rules I will follow
- No DELETE on notes or time; merge never rewrites history (see decision).
- Every new table carries `organization_id` where client-owned, forced RLS, isolation tests; every endpoint documented and tested; every change audited.
- Holidays affect **new and resumed** clocks only. Existing due dates are not silently rewritten. (A one-off "recalculate open tickets" button is an option later.)
- CSAT links are single-use tokens (like the portal links), expire, and never reveal other tickets.
- No new dependencies.

## 4. Decisions needed (hard to change later)
1. **Statuses.** (a) Keep five fixed, editable labels only. (b) **Recommended:** add your own statuses, each mapped to one of the five built-in behaviours (e.g. "Waiting on vendor" behaves like waiting, "Scheduled" behaves like open), so SLA, reopen, reports and the dashboard keep working. Tickets would store a status reference; existing data migrates 1:1. (c) Fully free-form workflows: not recommended (every report and rule becomes ambiguous).
2. **Merge.** (a) **Recommended:** "close as duplicate": link both tickets, copy a pointer note, close the source, and keep every note and time entry on the ticket where it was written (preserves the immutable-history guarantee; time stays billable where it was logged). (b) True merge that moves notes and time onto the target: needs UPDATE rights on notes/time, which weakens immutability and billing traceability.
3. **Custom fields**: in this phase, or later? They are the biggest data-model addition (values stored as validated JSON on the ticket; filtering by them is limited to simple equality at first).
4. **CSAT**: include now, or later? It needs outbound email and a public (token) page.

## 5. Decisions (from you)
1. **Statuses:** custom statuses, each mapped to one of the five built-in behaviours.
2. **Merge:** close as duplicate; notes and time stay where they were written.
3. **Custom ticket types and fields:** included.
4. **CSAT:** included. **Escalation on SLA breach:** included. **Auto-acknowledgement:** included.

## 6. Progress
- **Slice A done:** canned responses (Settings, note-box picker, `{{contact_name}}` / `{{ticket_number}}`), paging and sorting on the ticket list, bulk actions (up to 100, per-ticket results), global search. Checklist: [verify/tickets-phase1a.md](verify/tickets-phase1a.md).
- **Slice B done, with one change from the plan:** holiday calendar (closed or shortened days; affects new and recomputed SLA clocks only), auto-acknowledgement (off by default; known clients only; once per ticket; max 3 per address per day), escalation on SLA breach (email to a configured address, optional one-step priority bump, once per ticket). Checklist: [verify/tickets-phase1b.md](verify/tickets-phase1b.md).
- **Not built: outbound `In-Reply-To`/`References` headers and the `Auto-Submitted` header.** Microsoft Graph's `sendMail` only accepts custom headers that start with `x-`, so they cannot be set that way. Replies already thread through the `[#number]` subject tag (and our inbound side also matches by headers). Auto-replies carry `X-Auto-Response-Suppress: All` and `X-PSA-Auto-Reply`, which Exchange honours and our own inbound filter treats as automated. True header threading needs Graph's createReply flow, which I cannot test without a live tenant; it is in BACKLOG.
- Fixed a dead counter name (`ticket_created_unmatched`) in the mailbox ingest statistics.
- **Slice C done:** custom statuses (each mapped to one of the five built-in behaviours; behaviour is fixed at creation; the last active status of a behaviour cannot be archived; a DB trigger keeps `status` and `status_id` consistent) and ticket types with custom fields (text, number, date, dropdown, checkbox). Values live on the ticket as JSON keyed by field id, so renames lose nothing; fields are archived, never deleted; archived or other-type fields keep their stored values but are hidden and not validated. Required fields are enforced when a ticket gets a type or its values are edited. Fields marked "show to client" appear (when filled) on the portal ticket. Checklist: [verify/tickets-phase1c.md](verify/tickets-phase1c.md).
- **Things to know about slice C:** custom status names are visible to clients in the portal; field type cannot change after creation (create a new field instead); list filtering is by type only. Filtering by a custom field's value is in BACKLOG.
