# Tickets slice A (list, canned responses, bulk, search): what to verify manually

Sign in as admin first, then repeat the permission checks as a read-only user.

## Ticket list
- [ ] Click the **#**, **Priority** and **SLA due** headers: order changes, the arrow flips on a second click, rows with no SLA due date stay last
- [ ] With more than 50 tickets, **Next / Previous** page and the "x–y of N" text is right; changing a filter returns to page 1
- [ ] Read-only users see no checkboxes

## Bulk actions
- [ ] Tick several tickets (and "select all"): the blue bar shows the count
- [ ] Choose a status, priority, assignee or queue and **Apply**: every ticket changes; the ticket audit trail has one entry per ticket plus a bulk entry
- [ ] **Close N** closes them all
- [ ] Include a ticket you cannot change (for example in a state that rejects the change): the others still update and the failure is listed by ticket id
- [ ] Selecting more than 100 is refused

## Canned responses
- [ ] Settings > Canned responses: add one using `{{contact_name}}` and `{{ticket_number}}`; a duplicate name is refused; archive and restore work
- [ ] On a ticket, the note box shows **Insert canned response**; picking one fills the text with the contact's name and the ticket number (or "there" when the ticket has no contact); you can edit before saving
- [ ] Archived responses disappear from the picker; techs can use but not manage them

## Search
- [ ] Type in the sidebar search and press Enter: results grouped as Tickets, Clients, Contacts, Devices
- [ ] A ticket number (with or without #) finds that ticket
- [ ] Typing `%` or `_` matches those characters only, not "everything"
- [ ] A role without client access does not get client, contact or device results
