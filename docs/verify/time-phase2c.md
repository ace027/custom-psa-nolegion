# Phase 2C verification: expenses, mileage, receipts

Set up once: Settings → **Mileage rate** (e.g. 67 cents) and check **Expense categories**. Give a client a tax rate (Billing → client) and make sure Settings has your company name.

1. **My expenses** → add Expense: Travel, $123.45, "Parking", client Acme, tick **Bill to client**, **Taxable**, Markup 15. Attach a PNG or PDF receipt. The list shows cost $123.45 and billed $141.97 (+15%), with the receipt link.
2. Add Mileage: 37.5 miles, "Site visit". It shows $25.13 (at 67 c). With the rate at 0, mileage is refused ("Set the mileage rate in Settings").
3. Change the rate in Settings; the old trip keeps its amount.
4. Try a `.gif` or a renamed text file as a receipt: refused. A bad receipt does not lose the expense (you are told the receipt failed).
5. Billing → create an invoice for Acme with unbilled items. Expect one line "Travel: Parking (date)" at $141.97, tax $11.71, total $153.68; the mileage line (if billable) at cost, untaxed.
6. The expense now shows "invoiced" and cannot be edited or voided. Delete the draft line (or void the invoice): it is released and shows up in the next invoice.
7. Billing → Reports → Unbilled includes an Expenses column (billed price) and the CSV has expenses columns.
8. Submit the week in **My timesheet**: new expenses dated in it are refused until an admin returns the week. A week with only expenses can be submitted.
9. As admin, approve the week. **Download reimbursable expenses CSV** has the cost ($123.45, not $141.97), only expenses ticked "Reimburse me", only from approved weeks.
10. Another tech cannot see your expenses or receipts (403); an admin can. Audit log shows `expense.create/update/void/receipt_add`.
11. Billing runs bill expenses whether or not the week was approved.

Automated: `backend/tests/test_expenses.py` (23 tests, including the billing arithmetic above and a row-level-security isolation test), `frontend/src/Phase2A.test.tsx`.
