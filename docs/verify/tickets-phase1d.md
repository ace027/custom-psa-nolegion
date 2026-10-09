# Manual verification: tickets phase 1D (links, close as duplicate, CSAT)

Sign in as an admin. Use a client that has a contact with an email address you can read.

## Links
1. Open ticket A → **Linked tickets**. Choose "related to", enter ticket B's number, **Link**. B shows up with "Related to". Open B: A is listed there too.
2. Link A as "the parent of" C. Open C: A is listed as **Parent**.
3. Try to link C as the parent of A: refused (cycle). Try to link A to itself, to a ticket of a different client, or to a number that doesn't exist: each refused with a plain message.
4. **Unlink** one: it disappears from both tickets; both tickets are unchanged. Audit page shows `ticket.link_add` / `ticket.link_remove`.

## Close as duplicate
1. On ticket D (with a note and some logged time) use **Close as duplicate of ticket number** with ticket E's number.
2. D is closed and shows E as "Duplicate of"; E shows D as "Has duplicate".
3. Both tickets have an internal pointer note. D keeps its own notes and time; E gained none of them. Invoice preview still bills D's time on D.
4. A client viewing either ticket in the portal sees none of the pointer notes.
5. Repeat on an already-closed ticket, or pointing at a ticket that is itself a duplicate: refused.

## Satisfaction survey (needs the mailbox connected to actually send)
1. Settings → Auto-acknowledgement and escalation → tick the satisfaction survey option, Save.
2. Resolve a ticket whose contact has an email address. Within a minute the worker sends "[#number] How did we do?" with five links (5 to 1). Resolving a ticket with no contact or requester address sends nothing.
3. Open a link: the page shows your rating preselected. Nothing is recorded yet (check the ticket: still "not answered"). Add a comment and **Send feedback**: "Thank you".
4. Reload the page or use another link from the same email: the link no longer works (single use).
5. The ticket shows "Customer satisfaction: N of 5 … comment". The Dashboard shows the average and counts.
6. Reopen the ticket and resolve it again: no second survey. Wait 30 days (or set `expires_at` in the past in the database): the link says it has expired.
7. Switch the option off: new resolves send nothing; existing links still work until they expire.
