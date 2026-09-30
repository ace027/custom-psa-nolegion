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
- **Agreements** in force at any point in the month: `unit price x quantity`, **as the quantity is on the day you start the run**. **No proration**: an agreement that starts or ends mid-month is billed for the full month; adjust the draft in review (edit the quantity/price, or add a credit line).
- **Billable time** logged up to the end of the month, grouped by ticket and work type, at the client's hourly rate override or the work type's default rate.
- **One-off product charges** dated up to the end of the month.

**Never billed silently at $0:** a work type with no hourly rate leaves its time **unbilled** and adds a warning to the run. Fix the rate (Billing > Rates), then use *Add unbilled time and charges* on the draft.

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

## Not built (by design or deferred)
No payment recording or A/R aging, no emailing of invoices, no accounting/payment integrations, no
proration, one tax rate per client (no per-state/jurisdiction tax), no late fees, fixed invoice number
format. See `docs/BACKLOG.md`.
