# Manual verification: tickets phase 1C (statuses, types, custom fields)

Sign in as an admin. Seed data is fine; nothing here needs live mail.

## Custom statuses
1. Settings → **Ticket statuses**: five built-ins are listed with what they behave like.
2. Add "Waiting on vendor" behaving like *waiting on customer*. It appears in a ticket's Status picker and the list filter.
3. Put a ticket in it: the SLA clock pauses (SLA badge shows paused). Move it back to Open: the clock resumes.
4. Rename the status; the ticket shows the new name. Try to change its behaviour: not offered.
5. Try to archive the only active status of a behaviour: refused with a message. Archive "Waiting on vendor": tickets in it keep it; it is no longer offered for new choices.
6. Open the client portal for a contact on that ticket: it shows the status *name* (this is intended, so pick names you are happy for clients to see).

## Ticket types and custom fields
1. Settings → **Ticket types and custom fields** → add type "New hire".
2. Open **Fields** and add: "Start date" (date, required), "Laptop" (dropdown: Dell, HP), "Needs VPN" (checkbox), "Manager" (text, *show to client*).
3. Open a ticket → **Type and custom fields** card → choose New hire. The four inputs appear. Click **Save** without a start date: the error names the required field. Fill it in and save: it sticks after a reload.
4. Enter an impossible date or a dropdown value by API (`PATCH /api/tickets/{id}` with a bad `custom_values`): 409 with a plain message.
5. Change the ticket to another type, then back: the earlier answers return. Set type to None: the card hides the fields, but `GET /api/tickets/{id}` still shows the stored values.
6. Archive "Laptop": it disappears from the ticket, values stay in the database. Restore it: it comes back.
7. Ticket list: the **Type** filter (shown once a type exists) narrows the list.
8. Portal: sign in as the ticket's contact. The ticket shows **Details → Manager** only (not the other fields, and not empty ones).
9. As a tech: you can fill values, but cannot create or change types and fields (403). As read-only: cannot edit values either.
10. Audit page: `ticket_type.*`, `custom_field.*` and `ticket.update` entries exist for the above.
