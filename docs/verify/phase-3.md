# Phase 3: what to verify manually

Prep: dev stack with seed data (the seed sets demo rates, three agreements, a product sale and a company
name), signed in as `billing@example.com`. For the browser test, use a **freshly seeded** database.

## Setup screens
- [ ] Settings (as admin): **Invoicing** card shows your company name/address/footer; clear the name and confirm finalizing is refused with a clear message
- [ ] Billing > Rates: Remote / Onsite / After hours have hourly rates; clear one and see it show "not set"
- [ ] Organization page > **Billing**: payment terms and tax rate save; a per-client rate override shows and can be cleared
- [ ] Billing > Products: add a product; archive/restore; as `tech` the cost is **not** shown
- [ ] Billing > Agreements: create a per-user, per-device and a flat agreement; change a quantity with a reason and open **history**; "end" an agreement

## Time and products
- [ ] Log 20 min on a ticket: it shows Billable 30 min. Add a product to the ticket (Parts and products)
- [ ] After it is invoiced, the time entry can no longer be edited or voided

## The monthly run
- [ ] Start a run for the current month: one draft per client with something to bill; clients with nothing are absent
- [ ] Warnings are shown (try: a work type with no rate + time logged on it: the time is NOT billed at $0)
- [ ] Agreement lines show the quantity at run time; edit an agreement quantity afterwards: the draft does NOT change
- [ ] Open a draft: edit a line quantity/price/tax %, add a manual line, add a credit (negative price), remove a line. Totals update; each line's amount matches quantity x price
- [ ] Mark reviewed, then edit any draft: the run drops back to "draft" and must be reviewed again
- [ ] Try to start a second run for the same month: refused
- [ ] Finalize: invoices are numbered `INV-YYYY-0001...` in client-name order with no gaps; due date = invoice date + terms
- [ ] Finalized invoices show no edit controls and say "frozen"; voiding one needs a reason and keeps its number; its time/products become billable again
- [ ] Cancel a different (unfinalized) run: everything is released and the month can be run again
- [ ] Try a finalize that must fail (add a large credit so a total goes negative): *nothing* is finalized and the counter did not advance

## The PDF (send one to yourself)
- [ ] Company, bill-to, invoice #, dates, terms, lines, tax, totals and footer look right; drafts are watermarked DRAFT, voids VOID
- [ ] Arithmetic on the PDF matches a hand calculation for at least one invoice with tax
- [ ] Edit the client's name and your company name afterwards: the old finalized PDF is unchanged

## Roles
- [ ] `tech`: can add product charges to a ticket; can read invoices; cannot edit/finalize anything in Billing
- [ ] `read_only`: can view runs/invoices/agreements; no buttons
- [ ] `billing`: full billing access, but not Settings (company details are admin-only)
- [ ] Audit log shows every billing action (run create/review/finalize/cancel, invoice finalize/void, line edits with before/after, rate and tax changes, quantity changes)

## Ops
- [ ] `docker compose up -d --build` picks up migration 0003 and PDFs download (verified in the dev sandbox; check on your VM)
- [ ] Backup then restore drill (`docs/BACKUP_RESTORE.md`): after restoring, invoices, numbers and the "frozen" rule are intact
