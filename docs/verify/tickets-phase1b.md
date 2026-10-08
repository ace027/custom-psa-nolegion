# Tickets slice B (holidays, auto-acknowledgement, escalation): what to verify manually

## Holidays
- [ ] Settings > Holidays: add a closed day (for example next Monday) and a half day with hours; duplicates of a date are refused; Remove works
- [ ] Create a ticket whose SLA would run across the closed day: its due date skips that day
- [ ] A ticket created before you added the holiday keeps its old due date until its priority or pause state changes
- [ ] A holiday on a Saturday/Sunday (non-business day) changes nothing
- [ ] Read-only and tech users can see holidays but not add or remove them

## Auto-acknowledgement (needs the mailbox configured)
- [ ] It is OFF until you tick the box in Settings > Auto-acknowledgement and escalation
- [ ] Email the support mailbox from a known contact: a new ticket appears and one confirmation arrives, subject starting `[#number]`, with the contact's name
- [ ] Replying to that confirmation adds a note to the same ticket (and does not create a second one)
- [ ] Email from an address that is not a contact: ticket goes to triage and NO confirmation is sent
- [ ] An out-of-office or other automatic message creates nothing and gets no reply
- [ ] Five new emails from the same contact within a day: five tickets, only three confirmations
- [ ] A placeholder that does not exist (for example `{nope}`) is refused when saving

## Escalation
- [ ] Leave the address blank and the bump off: breached tickets cause no escalation email
- [ ] Set an address: within a worker cycle after a ticket breaches, that address gets one email naming the ticket; it is not repeated
- [ ] Resolved and closed tickets are never escalated
- [ ] With "raise the priority" on: the breached ticket's priority goes up one step once, and the ticket history shows who/what changed it (the system)
- [ ] Turning escalation on escalates tickets that are already breached (expected; do it at a quiet time)
