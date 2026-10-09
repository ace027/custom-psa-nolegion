# Client portal

A small, separate site at `/portal` where a client's people can open and follow tickets and, if they are
billing contacts, see invoices and download PDFs and an account statement. It is **off until you turn it
on** (Settings > Client portal) and needs the mailbox configured, because sign-in links are emailed.

## Who gets in
- Only a **contact you have given portal access** (Organizations > contact > *Give portal access*). Giving
  access is **admin-only** (`portal:manage`); anyone who can edit contacts can *remove* it.
- The contact needs an email address. An email address can have portal access for **one client at a
  time** (the sign-in link names no organization, so the database enforces this).
- Contacts see **their own tickets**. Tick *See all company tickets* (admin) for a manager who should see
  every ticket their company has opened.
- **Invoices, invoice PDFs and the statement are for contacts marked as billing contacts only.** Drafts and
  voided invoices are never shown.

## How signing in works (no passwords)
1. The person enters their email at `/portal`. The answer is always the same ("if that address has portal
   access, a link is on its way"), so the form cannot be used to find out who has access.
2. If it matches, the worker emails a link. It is **single use**, valid **15 minutes**, stored only as a hash,
   and carries its token in the URL *fragment* (`#token=...`) so it is not sent to servers, logs or
   referrers. Opening the page redeems it with a POST (so mail scanners that prefetch links cannot use it up).
3. A portal session cookie (`psa_portal`, HttpOnly, SameSite=Lax, Secure in production) lasts 8 hours.
   Every request re-checks that the contact and client are still active and portal access is still on, so
   removing access, archiving the contact or client, or switching the portal off ends sessions immediately.
- Limits: at most 3 links per contact and 20 per IP per hour; 20 new tickets and 50 replies per contact
  per day. Sign-in requests, sign-ins, failures and denials are all in the audit log (`portal.*`).

## What keeps clients apart
- The portal principal is scoped to exactly one organization in the application **and** in PostgreSQL
  row-level security, the same backstop as staff data. A ticket or invoice from another client looks
  exactly like one that does not exist (404).
- Only customer-visible information leaves the building: never internal notes, assignees, SLA clocks, time
  entries, product costs or other clients' data. Staff and portal sessions are separate cookies and tables;
  neither works on the other's API.
- Everything a client does is recorded (`portal.ticket_create`, `portal.ticket_reply`) with the contact id.

## Decisions worth a second look
- Tickets opened in the portal appear in your normal unassigned queue (source *portal*); nobody is emailed
  about them yet (backlog: new-ticket alert).
- A client's reply reopens a waiting/resolved/closed ticket, exactly like an emailed reply.
- No file uploads, no online payment (payments are still recorded by hand), no self-service contact management.
- Someone who controls the mailbox of a portal contact can sign in as them. That is the same trust
  model as email replies to tickets; keep portal access to people whose mailboxes you trust.
- A sign-in request from a known address does slightly more work than one from an unknown address, so
  response *timing* could in theory hint at whether an address has access. The content never does.
