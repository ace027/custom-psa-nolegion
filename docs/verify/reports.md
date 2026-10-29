# Reports: what to verify manually

Prep: seed data plus a few finalized invoices, some unbilled time and one-off charges, and an agreement. Sign in as `billing@example.com`.

- [ ] Billing > Reports exists for billing/admin; `tech@example.com` does not see the tab and `/api/reports/revenue` returns 403
- [ ] Revenue: client totals match the invoices you finalized; a voided invoice and a draft are not counted; tax is a separate column
- [ ] Set From/To: the table and CSV follow the range; more than 60 months is refused
- [ ] Unbilled: log billable time and add a charge: they appear; invoice them: they leave the report
- [ ] A work type with no rate shows "(x unpriced)" hours, not $0
- [ ] Recurring: this month's *contracted* equals your active agreements (quantity x price); after finalizing the monthly run, *invoiced* matches
- [ ] Invoices CSV opens in a spreadsheet: numbers as dollars, dates as YYYY-MM-DD, balance matches Receivables
- [ ] Create a client named `=1+1`: in the CSV it is shown as text (`'=1+1`), not calculated
- [ ] Audit log shows a `report.export` row for each CSV download (none for just viewing)

## Management reports, dashboards and scheduled emails (Phase 11)

Needs: an admin login, a billing login, a tech login, some tickets with SLA targets, time entries, finalized invoices, and a way to run the worker once. Definitions are in `docs/REPORTS.md`.

## SLA
- [ ] Reports > SLA report shows this month. Change the range and group by priority, client and assignee.
- [ ] Pick one row and count its tickets by hand. Met, breached, pending and no-SLA add up to the ticket count.
- [ ] A percentage shows as `xx.xx% (n=N)` and a group with nothing to measure shows `-`.
- [ ] Download CSV opens a file with the same rows and range.

## Utilisation
- [ ] Utilisation report: pick a technician and add up their time entries by hand. Logged matches.
- [ ] Capacity matches their work hours minus holidays and time off.

## Aging
- [ ] Aging report total equals Billing > Receivables total. Buckets match days past due.

## Profitability
- [ ] Users > Edit on a technician > Cost rate (per hour): set $90.00 and save.
- [ ] Log 50 minutes on a billed client's ticket. Profitability labour grows by $75.00.
- [ ] A technician with no cost rate shows "No cost rate" minutes instead of a silent $0.
- [ ] Revenue equals Billing > Reports revenue for the same dates.
- [ ] The cost-rate field is not visible to billing or tech users.

## Dashboards
- [ ] Tech login: Dashboard shows My week and no Business section.
- [ ] Billing/admin login: Business section shows revenue, margin, AR with buckets, unbilled, SLA 30-day with n, last-week utilisation. Tiles open the matching report.

## Scheduled reports
- [ ] Reports > Report schedules (admin): create a weekly schedule to yourself. Billing sees the list but no New or Edit buttons.
- [ ] Monthly day is limited to 1-28.
- [ ] A tech cannot be picked as a recipient.
- [ ] Run the worker on the scheduled day: one email with a CSV arrives, and Runs shows one row. Running the worker again sends nothing.
- [ ] Deactivate the schedule: nothing is sent next period.
