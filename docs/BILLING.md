# Billing: how it works and how to run it

## The rules (these are tested; change them only deliberately)
1. **Money is integer cents everywhere.** No floating point in billing code, the API or the database.
2. **Time**: billable minutes = actual minutes **rounded up** to the billing increment (Settings; default 15), fixed on each time entry when it is logged. Non-billable entries bill 0.
3. **Each invoice line**: `amount = round(quantity x unit price)`, then `tax = round(amount x tax rate)`. Ties round **half up, away from zero**, so a credit is the exact mirror of a charge. Tax is computed **per line on the rounded amount**.
4. **Invoice totals are plain sums of the lines** (subtotal = sum of amounts, tax = sum of line taxes). The invoice can never disagree with its own lines by a penny. (A single tax calculation over the whole subtotal could differ from the sum of line taxes by a few cents; the per-line rule is the one we follow.)
5. **Tax rate is a snapshot on the line** (basis points; 825 = 8.25%). Changing a client's rate later never changes existing drafts or finalized invoices. Each client has ONE rate; a line is taxed if its source is marked taxable (agreement / product / work type).
6. **Finalized invoices are immutable**, enforced by database triggers as well as the app. Corrections = **void and reissue**, or a **credit line** (negative manual line) on the next invoice.
7. **Invoice numbers** are `INV-YYYY-NNNN`, gap-free within a year, assigned only at finalize. The year comes from the invoice date. A voided invoice keeps its number (never reused).
8. **A month can be run once.** Only one non-cancelled billing run per month can exist, so an agreement period cannot be billed twice. (A database rule also forbids two live invoice lines for the same agreement and month.)
9. **Time and product charges are locked onto an invoice line** the moment they are invoiced (time entries can no longer be edited or voided). Removing the line, or voiding the invoice, releases them to be billed again.
10. **Snapshots**: at finalize, the client name/address, your company details and payment terms are copied onto the invoice, so editing them later never rewrites history.

## What goes on a monthly run
For each client, one **draft** invoice containing:
- **Agreements** in force at any point in the month: `unit price x quantity`, **as the quantity is on the day you start the run**. **Proration**: an agreement that starts or ends mid-month is billed as the full-month line plus a separate negative `proration` line for the calendar days not covered: `-round_half_up(quantity x unit price x days_not_covered / days_in_month)`, taxed at the same rate as the agreement. Starting on the 1st or ending on the last day creates no credit. Quantity changes *within* a month are not prorated; edit the draft. Example: 10 users x $150.00 from 15 Oct = $1,500.00 - $677.42 (14 of 31 days) = $822.58.
- **Billable time** logged up to the end of the month, grouped by ticket and work type, at the client's hourly rate override or the work type's default rate.
- **One-off product charges** dated up to the end of the month.
- **Billable expenses and mileage** dated up to the end of the month (see below).

**Never billed silently at $0:** a work type with no hourly rate leaves its time **unbilled** and adds a warning to the run. Fix the rate (Billing > Rates), then use *Add unbilled time and charges* on the draft.

### Billable expenses and mileage (phase 2C)
A billable expense becomes an ordinary **product** line (quantity 1) the same way a one-off charge does, so freezing, tax and voiding behave identically.
- Line price = cost + markup, the markup rounded half up to a cent: cost 12,345 c at 1,500 bp = 12,345 + 1,852 = **14,197 c**.
- Tax is per line on that rounded price at the client's rate when the expense is marked taxable: 14,197 c at 825 bp = **1,171 c**, line total 15,368 c.
- Mileage = miles x the rate copied from Settings when entered (67 c/mile: 37.5 mi = 2,513 c; 12.35 mi = 827 c; 0.5 mi = 34 c), billed at cost unless a markup is set.
- Pulled by the same generation as time and charges (dated on or before the run end, not voided, not already invoiced). Timesheet approval does **not** gate it. Voiding the invoice or deleting the draft line releases the expense. The person is reimbursed the cost, never the marked-up price.

## The monthly procedure
Billing > Monthly runs
1. **Start billing run** for the month (the current or next month; "in advance" is normal).
2. Read the **warnings** at the top of the run, then open each invoice: check quantities (users/devices changed?), mid-month changes, credits owed. Edit lines, add manual lines, remove lines, add a memo. Use the PDF download to see exactly what the client will get.
3. **Mark reviewed.** *Any* later change to a draft in the run undoes the review, so what you finalize is what you reviewed.
4. **Finalize all invoices.** All-or-nothing: if any invoice can't be finalized (e.g. a negative total), nothing is finalized and no numbers are used. Fix it and try again.
5. Send the PDFs to clients yourself (emailing invoices from the PSA is not built; see the backlog).

Made a mistake before finalizing? **Cancel run**: its drafts are discarded, all time and charges are released, and the month is free to run again.
Made a mistake after finalizing? **Void** the invoice (a reason is required), then create a one-off invoice (Billing > Invoices > New one-off invoice) to reissue. The month stays "run"; you never run it twice.

## One-off invoices
Billing > Invoices > *New one-off invoice for*: a draft that pulls in the client's unbilled time and product charges up to today; add manual lines as needed; finalize it. Use this for projects, hardware sales between runs, and reissuing a voided invoice.

## Where each thing is set
| What | Where | Who |
|---|---|---|
| Company name, address, invoice footer | Settings > Invoicing | admin (needs `config:manage`) |
| Business time zone, billing increment | Settings | admin |
| Hourly rate and taxability per work type | Billing > Rates | admin, billing |
| Client payment terms, tax rate, rate overrides | Organization page > Billing | admin, billing |
| Agreements (per user / per device / flat) | Billing > Agreements | admin, billing |
| Product catalog (price, cost) | Billing > Products | admin, billing (cost is hidden from other roles) |
| Sell a product on a ticket | Ticket page > Parts and products | admin, tech, billing |
| Review / finalize runs, finalize or void invoices | Billing | admin, billing |

## Worked example
Client tax rate 8.25%; agreement "Managed Services" 12 users x $12.00 (taxable); 0.5 h After-hours at $225.00 (labor not taxable); a $10.00 credit:

| Line | Amount | Tax |
|---|---|---|
| Managed Services: 12 users x $12.00 | $144.00 | $11.88 (8.25% of 144.00) |
| Ticket #10001 (After hours), 0.5 h x $225.00 | $112.50 | - |
| Goodwill credit | -$10.00 | - |
| **Subtotal $246.50, tax $11.88, total $258.38** | | |

## Payments and receivables
**An invoice's balance is never stored on the invoice** (finalized invoices are frozen). It is always
`invoice total - payments applied - write-offs`, worked out from the records below.

| Record | What it is | Can it be edited? |
|---|---|---|
| **Payment** | Money received from a client: amount, date, method (check/ACH/card/cash/other), reference | No. Void it (reason required) and record it again |
| **Application** | The part of a payment that pays a particular invoice | No. Undo it (reason required); the money returns to the payment as credit |
| **Write-off** | An uncollectible balance you give up on, with a required reason | No. Reverse it (reason required) |

Rules (enforced by database triggers as well as the app, including under simultaneous requests):
- A payment can be **split across several invoices** and can be **partial**; whatever is not applied stays as **credit** on the client's account, to be applied to a later invoice.
- Money can only be applied to a **finalized** invoice **of the same client**, never more than the invoice's remaining balance, and never more than the payment's unapplied amount.
- An invoice with payments or write-offs on it **cannot be voided**: undo those first (so nothing is ever left pointing at a void invoice).
- A payment cannot be dated in the future (your business time zone). Leave the date blank for today.
- Voiding a payment undoes all of its applications: the invoices it paid become open again.

Invoice payment status: **unpaid** (nothing received), **partial**, **paid** (balance 0), **written off**
(balance 0 after a write-off). **Overdue** = balance > 0 and past the due date.

**Receivables** (Billing > Receivables) groups open balances by client into Current (not yet due),
1-30, 31-60, 61-90 and 90+ days **past the due date**, and shows each client's unapplied credit. The
Billing tab shows how many invoices are overdue. Filter the Invoices list by Payment (owes money /
overdue / nothing paid / paid).

Recording a payment: Billing > Payments (or *Record payment* on an invoice or a receivables row).
Pick the client, enter the amount, then *Auto-apply, oldest first* or type amounts per invoice; the
form tells you how much will be kept as credit. To use credit later: Payments > details > *Apply credit*.

The invoice PDF is the document you issued and does not change when payments arrive (no PAID stamp or
running balance); a *statement* (below) shows the current position.

## Statements and payment reminders
**Nothing is ever emailed without a person approving it.** The worker only *prepares* notices; you read,
edit if you like, and approve them on Billing > Reminders. Approved notices go through the normal outbox
(sent by the worker from the support mailbox, so a client's reply arrives as a ticket).

- **Reminders.** Default schedule: 1, 15, 30 and 60 days past due (Friendly reminder, Follow-up, Second
  notice, Final notice). Edit days, wording or switch a stage off under Settings. Each stage is issued **at
  most once per invoice**; a client gets **one** notice listing all their overdue invoices, using the
  highest stage newly reached (never a lower stage after a higher one), and is not re-reminded within
  the *minimum gap* (default 7 days). Clients marked **Do not send payment reminders**, archived clients
  and fully paid invoices are skipped. Editing days does not re-issue stages already sent.
- **Recipients.** The client's billing contacts; if none, the primary contact. If nobody has an email the
  notice is **blocked** and cannot be sent (the app never guesses an address).
- **Stale notices.** If a payment or void changes the numbers after a notice was prepared, it is marked
  stale and must be *Refreshed* (text is regenerated from the template) before it can be sent. If
  everything was paid it expires instead.
- **Attachments.** The invoice PDFs (up to 10); over that, a statement PDF.
- **Statements.** A statement is a frozen snapshot: open invoices with days late, payments since the last
  statement (first one looks back 90 days), unapplied credit, and an aging summary, with a PDF. Generate
  one from Receivables or the client page (*Statement PDF*), or *Prepare statement email* to review and send it.
  The monthly batch (Prepare monthly statements, or automatic on the 1st when enabled) prepares one per client
  with a balance or credit, once per month.
- **Invoice emails.** On any finalized invoice, *Prepare email to client* queues an email with the invoice
  PDF for review (same recipients rule; one waiting email per invoice, enforced by the database; a voided
  invoice cannot be sent). Optionally (Settings, off by default) one is prepared automatically whenever an
  invoice is finalized, including every invoice in a billing run; it is still only sent when you approve it.
- **Templates.** Placeholders in `{braces}` are checked when saved (unknown ones are refused).
- **Permissions.** billing:write prepares/edits/refreshes; billing:finalize approves (sends) or dismisses
  (with a reason). Everything is audited (`notice.*`, `statement.create`, `reminder_stage.update`).
- **Records.** Statements, sent/dismissed notices and the exact PDF bytes that were emailed cannot be changed
  or deleted (database triggers), so you can show what a client was told.

## Reports and CSV exports
Billing > Reports (admin and billing roles only: the `report:read` permission; techs and read-only
users do not get revenue figures). Every CSV is in dollars and each download is recorded in the audit
log (`report.export`). Cells that start with `=`, `+`, `-` or `@` are prefixed with `'` so a spreadsheet
never runs a client-supplied name as a formula.
- **Revenue:** finalized, non-void invoices by *invoice date* (not cash received), by client and by
  month, split into time / products / agreements / other, with tax shown separately. Default: last 12
  months; ranges over 60 months are refused.
- **Unbilled work:** billable time and one-off charges not yet on an invoice, priced at *today's*
  rates (client override, else the work type rate), before tax. Time with no rate anywhere is reported
  as unpriced hours, not as $0.
- **Recurring revenue:** per month, *contracted* (each agreement's current quantity x price, for
  agreements active that month, the same rule the run uses) next to *invoiced* (what agreement lines were
  actually billed for that month). Past quantity changes are not replayed, so use "invoiced" for history.
- **Invoice CSV:** one row per finalized or voided invoice by invoice date, with paid, written-off,
  balance and payment status, for your accountant. Nothing is sent to any accounting system.

## Not built (by design or deferred)
No automatic sending (every reminder/statement is approved by a person), no late fees, no accounting/payment-processor integrations (payments
are *recorded by hand*, nothing is charged or reconciled with a bank), one tax rate per
client (no per-state/jurisdiction tax), no late fees, no refunds as a separate record (void the
payment), fixed invoice number format. See `docs/BACKLOG.md`.
