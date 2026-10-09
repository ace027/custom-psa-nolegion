# Payment tracking: what to verify manually

Prep: dev stack with seed data and at least a few **finalized** invoices (run and finalize a billing run, or create one-off invoices), signed in as `billing@example.com`.

## Recording
- [ ] Billing > Payments > *Record a payment*: pick a client; its open invoices appear, oldest due first
- [ ] Enter an amount and click *Auto-apply, oldest first*: amounts fill in; the note says how much is left as credit ("Fully applied." when zero)
- [ ] Type more than the payment across invoices: it warns "Over-applied" and refuses to save
- [ ] Record a payment that fully pays one invoice: the invoice shows **paid**, balance $0, and lists the payment (method, reference)
- [ ] Record a *partial* payment: invoice shows **partial** and the right balance
- [ ] One payment split across two invoices works
- [ ] Overpay: the extra shows as **unapplied** credit on the Payments list and on Receivables; Payments > details > *Apply credit* applies it to another invoice
- [ ] Leave "Date received" blank: today's date (your business time zone) is used; a future date is refused

## Undoing (each needs a reason)
- [ ] On an invoice, *undo* a payment application: the invoice reopens and the money returns to the payment as credit
- [ ] *Void payment* (e.g. "check bounced"): every invoice it paid reopens; a voided payment shows struck through and can't be applied
- [ ] *Write off balance* (reason required): status becomes **written off**, balance $0; *reverse* it and the balance returns
- [ ] Try to *void an invoice* that has a payment or write-off on it: refused with "void those first"
- [ ] Payments can't be edited anywhere in the UI (only voided)

## Overdue and aging
- [ ] Finalize an invoice with an old invoice date (or Net 0) so it is past due: invoice shows "Nd overdue"
- [ ] Billing > Receivables: it sits in the right bucket (1-30, 31-60, 61-90, 90+); totals add up; a client with only credit still appears
- [ ] The Receivables tab shows the overdue count; Invoices > Payment filter (Owes money / Overdue / Nothing paid / Paid) works
- [ ] Organization page > Billing card shows that client's outstanding balance and credit
- [ ] Cross-check one client's numbers by hand against their invoices and payments

## Roles and audit
- [ ] `tech` / `read_only`: can see balances and Receivables but have no Record payment / Write off / Void buttons
- [ ] `billing`: can record and apply payments and void/write off; audit log shows `payment.create`, `payment.apply`, `payment.unapply`, `payment.void`, `invoice.write_off`, with reasons and who did it

## Ops
- [ ] `docker compose up -d --build` runs migration 0004; after a backup/restore drill, payments, applications and their immutability rules are intact
