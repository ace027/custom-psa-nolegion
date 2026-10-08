# Manual check: Phase 3C late fees

1. **Settings > Late fees**: percent 1.5, flat $10.00, grace 15 days, most fees 1. Save.
2. **Billing > Late fees**: nothing listed (clients are opted out by default).
3. On a client page > Billing, tick **Charge late fees to this client**. Finalize a $1,000.00 invoice dated so it is 40 days past due.
4. **Billing > Late fees** now lists it: balance $1,000.00, fee **$25.00** ($15.00 + $10.00). A 15-day-late invoice is not listed (grace is "more than 15").
5. Tick it and apply (billing/admin only; read-only users cannot). Expect a $25.00 non-taxable charge "Late fee on INV-...: 40 days overdue, 1.5% of $1,000.00, $10.00 flat" under Billing > Products > charges.
6. The list no longer shows that invoice (cap 1). Void the charge: it reappears. Apply again.
7. Create the next invoice for the client: the $25.00 appears as a line. Let it go overdue: it is **not** listed on its own (a fee is never charged on a fee).
8. Record a partial payment on the original: the fee shown is based on the remaining balance.
9. **Audit log** shows `late_fee.apply`.
