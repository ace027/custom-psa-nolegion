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
