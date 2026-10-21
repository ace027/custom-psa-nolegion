# CRM: leads, pipeline, forecast and renewals

The Sales area (`/crm`) is for staff with `crm:read`. Admins and techs also have `crm:write`; billing and read-only users can look but not change anything. Stage setup needs `config:manage` (admin).

All money here is an estimate for planning. Nothing in the CRM creates an invoice.

## Leads and conversion
A lead is a possible client who is not yet in the system: name, company, email, phone, source, owner, notes and a status of New, Contacted, Qualified or Disqualified.

Only a **Qualified** lead can be converted. Converting once:
- creates a client with status **prospect**, named after the company (or the lead's name if there is no company);
- adds the lead as the client's primary contact;
- creates an opportunity at the first active open stage, owned by the lead's owner (or you).

The lead becomes **Converted** and links to the new client. A converted lead is read-only and cannot be converted twice (the page shows the API's 409 message).

## Stages and probabilities
A stage has a name, position, probability and a kind: **open**, **won** or **lost**. The pipeline board shows one column per active stage in position order. A stage's probability is what the forecast weights open deals by (50% = 5000 basis points). Admins edit stages in Settings > Sales pipeline stages. The kind cannot be changed after a stage is created. Deactivating a stage hides its column; deals in it keep it.

## Opportunities
An opportunity belongs to a client and has a name, a kind, an owner, a monthly amount, a term in months, an expected close date and notes.
- **new**: a first agreement.
- **renewal**: created by the renewal scan for an agreement that is ending.
- **upsell**: more services for an existing client.

Move a deal with the stage select on its card (or on the opportunity page). Moving to a lost stage needs a reason; the form will not send without one. A closed (won or lost) opportunity is read-only until moved back to an open stage.

## Linking a quote
On the opportunity page, **Link a quote** offers the quotes of the same client (not declined or cancelled). You can also link from the quote page ("Opportunity" row). When the client **accepts** the linked quote:
- the opportunity moves to the won stage and is stamped with the close time;
- the agreement the quote created is attached to the opportunity (a renewal opportunity keeps the agreement it renews).

## Forecast math
Only open opportunities are forecast, grouped by expected close month. Past dates fall in an overdue group, far dates in "Later", and deals with no date in "No date".
- Monthly = the sum of monthly amounts.
- **Weighted monthly** = monthly x stage probability, rounded half up to the cent **per opportunity**, then summed.
- **Contract value** = monthly x term in months, per opportunity, summed.
- **Won this month / this quarter** = monthly amounts of opportunities won in that period (business time zone).

Example: $1,500.00 a month at 50% weighs $750.00 and has a contract value of $18,000.00 over 12 months.

## Renewals
The worker scans agreements that have an end date. Settings > Sales holds:
- **Renewal reminder days**: up to 5 different numbers of days before the end date (for example 90, 60, 30).
- **Renewal reminder email**: where the reminder email goes. Blank means no email.

When today reaches the end date minus a reminder day, the scan creates one reminder for that agreement and day (never twice) and, if the agreement has no open renewal opportunity, creates one (kind renewal, closing on the end date, monthly amount from the agreement, 12-month term). It queues one email per new reminder when an address is set. Reminders show on Sales > Renewals and the Dashboard "Renewals due" card, nearest end date first. A reminder becomes done when its renewal opportunity is won or lost. **Dismiss** removes a reminder you do not need.

## Permissions
| Action | Permission |
| --- | --- |
| See leads, pipeline, forecast, renewals, the client Opportunities card | `crm:read` |
| Add or edit leads and opportunities, convert, move stages, link quotes, dismiss reminders | `crm:write` |
| Edit stages | `config:manage` |
| Renewal days and email | `config:manage` (Settings) |
