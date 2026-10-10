# Staff notifications: what to verify manually

Prep: mailbox configured and the worker running (see MAIL_SETUP.md). Two staff users (tech and admin).

- [ ] As admin, assign a ticket to the tech: within a poll cycle the tech gets "PSA: ticket #N was assigned to you" with client, priority and a working link
- [ ] Assign a ticket to yourself: no email
- [ ] Customer replies to an assigned ticket: the assignee gets a "new reply" email that does NOT contain the reply text
- [ ] Reply to a notification email: it does not appear on the ticket as a customer reply
- [ ] Give a ticket a short SLA (or wait): assignee gets one "at risk" email, later one "breached"; no repeats each poll
- [ ] Unassigned, waiting-on-customer, and resolved tickets: no SLA emails
- [ ] Click your name > untick a box: that kind of email stops; the others continue
- [ ] Settings > untick "Email staff about their tickets": nothing more is sent
- [ ] With the mailbox unconfigured: nothing is queued (Settings > mailbox shows 0 outbound pending)
