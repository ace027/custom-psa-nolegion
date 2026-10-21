# Manual check: CRM and renewals (Phase 9)

Needs: an admin login, a read-only login, a way to run the worker once, and a mail address for the renewal email.

## Leads
- [ ] Sales > Leads > Add lead (name, company, email). It lists as New.
- [ ] Change its status to Qualified. A New lead has no Convert button; a Qualified one does.
- [ ] Convert: the form is prefilled from the lead. Enter $1,500.00 a month, 12 months, a close date. You land on the opportunity.
- [ ] Open Organizations: the client exists with status **prospect** and the lead as primary contact.
- [ ] Back on Leads the lead is Converted with a "View client" link and cannot be converted again.

## Pipeline
- [ ] Sales > Pipeline shows one column per active stage in order, the deal in the first.
- [ ] Move it through the stages with the card's select.
- [ ] Move another deal to Lost: it asks for a reason and refuses an empty one. With a reason it moves and shows on the opportunity page.
- [ ] The client page shows the deals in its Opportunities card; New opportunity adds one.

## Quote link and win
- [ ] Create and send a quote for the prospect client. On the opportunity page, Link a quote. The quote page shows the Opportunity row.
- [ ] Mark the quote accepted. The opportunity is now in the won stage and shows the new agreement.

## Forecast by hand
- [ ] Keep three open deals with known monthly amounts, terms and stages (for example $1,000 at 10%, $2,000 at 50%, $3,000 at 90%, all closing next month).
- [ ] Sales > Forecast: monthly $6,000.00; weighted $100.00 + $1,000.00 + $2,700.00 = $3,800.00; contract value = each monthly x its term, summed.
- [ ] Won this month and this quarter tiles include the deal you just won.

## Renewals
- [ ] Settings > Sales: reminder days `90, 60, 30` and your email. Save.
- [ ] Give an agreement an end date 60 days from today.
- [ ] Run the worker once. Sales > Renewals lists reminders for the 90 and 60 day marks, the Dashboard card shows it, a renewal opportunity exists on the client, and one email per reminder is queued to your address.
- [ ] Run the worker again: no duplicate reminders, opportunity or emails.
- [ ] Dismiss a reminder: it leaves the list.

## Permissions
- [ ] As the read-only user: Sales is visible, but no Add lead, Convert, stage selects, Save or Dismiss.
- [ ] Only the admin sees the Sales pipeline stages card in Settings.
