# Client portal: what to verify manually

Prep: mailbox configured and the worker running; two clients each with a contact; an admin login.

## Turning it on
- [ ] Settings > Client portal is off by default; while off, requesting a link sends no email and a link cannot be redeemed
- [ ] As a **tech**, the contact card has no *Give portal access* button; as **admin** it does
- [ ] Give portal access to a contact with an email: the card shows "portal". A contact without an email cannot be given access
- [ ] Give the same email portal access on a second client: refused

## Signing in
- [ ] Open `/portal`, enter the contact's email: the same message appears for a known and an unknown address
- [ ] The email arrives from the support mailbox; the link opens the portal and the address bar loses the `#token=...`
- [ ] Using the same link again, or after 15 minutes, says it expired
- [ ] Request 4 links in an hour: the 4th does not arrive
- [ ] *Sign out* works; the back button does not show data
- [ ] Remove the contact's portal access (or switch the portal off) while signed in: the next click asks to sign in again

## What they see
- [ ] Non-billing contact: Tickets only, no Invoices tab; opening `/api/portal/invoices` directly is refused
- [ ] Billing contact: Invoices with status and balance, invoice PDF, account statement PDF; no drafts or voided invoices
- [ ] A contact sees only their own tickets; *See all company tickets* widens that to their company only
- [ ] Add an internal note and a customer note on a ticket in the staff UI: only the customer note shows in the portal
- [ ] Nothing from the other client is ever visible (try their ticket id in the URL: "not found")

## Doing things
- [ ] Open a ticket in the portal: it appears in the staff Tickets list as *portal* with the right client and contact
- [ ] Reply in the portal: the staff ticket gets a customer-visible note and reopens if it was waiting/resolved; the assignee gets the "new reply" email
- [ ] Audit log shows portal.login_link_requested, portal.login, portal.ticket_create, portal.ticket_reply
