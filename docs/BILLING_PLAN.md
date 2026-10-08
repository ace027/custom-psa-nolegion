# Phase 3: contract and billing depth: money rules for your approval

Status: **proposal. No code is written. Billing math is the highest-regret area, so every rule below is spelled out with a worked example. Tell me which to build, and veto or change any rule.** Part of [PARITY_ROADMAP.md](PARITY_ROADMAP.md).

All of [BILLING.md](BILLING.md)'s existing rules stay: integer cents, per-line `round_half_up` amounts and tax, immutable finalized invoices (void and reissue), gap-free numbers, one run per month, no payment-processor or accounting integrations.

## 1. Where things stand (verified in code)
- Agreements are `flat`, `per_user` or `per_device`: `unit price x quantity`, **one full month, no proration**, quantity as of the day the run starts. A quantity change is logged.
- One tax rate per client; a line is taxed or not (agreement / product / work type flag). Rate is snapshotted on the line.
- A mistake is fixed by voiding the invoice, or a **negative manual line** on the next invoice. There is no credit document and no refund record.
- Payments are recorded by hand, applied to invoices, voidable. Write-offs reduce an invoice balance with a reason.
- NinjaOne assets sync into `assets` per client, but nothing connects them to agreement quantities.

## 2. Proposed slices (build one at a time, each tested and documented)

### A. Proration and device counts (lowest regret; recommended first)
**Proration of a mid-month start or end.** Days are calendar days, inclusive. The agreement still bills as one full-month line, plus a **separate negative "proration" line** for the part not covered, so the client sees both and every amount stays an exact integer:
`credit = round_half_up(quantity x unit_price x (days_not_covered / days_in_month))`, taxed like its agreement at the same rate (a negative line mirrors a positive one).
- Example: 10 users at $150.00 (15,000 c) start on 15 Oct (October has 31 days, active 17 days, not covered 14). Full line 150,000 c. Credit = 150,000 x 14/31 = 67,741.935... = **-67,742 c**. Net **82,258 c** ($822.58). If taxable at 8.25%: tax on 150,000 = 12,375, tax on -67,742 = -5,588.715 -> -5,589, net tax **6,786**.
- Starting on the 1st or ending on the last day: no credit line. If an agreement both starts and ends inside the month, one credit covers the days outside.
- Mid-month **quantity changes** stay as today (quantity on the day the run starts); you adjust the draft. I will not guess intent there.

**Device counts from NinjaOne.** On a `per_device` agreement, the run review shows "NinjaOne reports 42 devices, agreement says 40" with a one-click **Update quantity** (which writes the usual quantity log). **Nothing changes quantities or money automatically.** Counts use synced assets for that client, optionally limited by device kind.

### B. Credit memos and refunds
**Credit memo** = a first-class, numbered (`CM-YYYY-NNNN`, gap-free), immutable document with a reason and one or more lines (positive amounts, tax per line, mirror of an invoice). It reduces what the client owes: you **apply** it to specific open invoices (like a payment application) and any remainder stays as **client credit** you can apply later. Voiding a memo (with reason) reverses its applications. This replaces "negative manual line" for corrections after finalize, which stays available.
- Example: invoice INV-2026-0042 total 15,368 c is overbilled by one 14,197 c line (tax 1,171). Credit memo of that line + tax = 15,368 c, applied to 0042: balance goes to 0. Never edits 0042.

**Refunds.** A refund records money you **paid back** to a client against a payment (by hand: check, ACH, whatever; nothing is sent anywhere). It reduces net payments received, can restore an invoice balance if the payment was applied, and cannot exceed the unrefunded part of the payment. Not the same as voiding a payment recorded by mistake.

### C. Late fees
Off by default, per client opt-in. Rule you set in Settings: percent of the overdue **invoice balance** (basis points) and/or a flat fee, a grace period in days, and a cap of how many times per invoice. **A person approves each fee batch** (like reminders): the screen lists "Invoice 0042, 21 days overdue, balance $1,000.00, fee 1.5% = $15.00" and you tick which to apply. Applying creates an ordinary product charge billed on the next invoice (never edits the overdue invoice, never compounds on earlier fees: the base excludes fee lines).
- Example: balance 100,000 c, 150 bp -> 1,500 c ($15.00); flat $10 added -> 2,500 c.

### D. Block-hour / retainer agreements
New agreement type `block`: a fixed monthly price including N hours. Time for that client **in the month** is consumed against the block in work-date order; hours beyond N bill at the normal rate as overage; the block price bills every month regardless of use.
- Example: $1,000/month for 10 h. 12.5 h logged -> block line $1,000, overage 2.5 h at $150 = $375.
- **Decision for you:** unused hours expire at month end, or roll over (and for how long)? Rollover needs a balance ledger; expiry does not. I recommend expiry first.
- **Decision for you:** do work types or tickets ever sit outside the block (for example after-hours at a premium)? Recommended: block covers all billable time except work types you mark "not covered by blocks".

### E. Multiple tax rates (decide before I build)
Today: one rate per client, items either taxable or not. If you sell to clients in several jurisdictions that already works (set each client's rate). It does **not** cover one client being charged state + county + city as separate lines, or goods taxed differently from services. Options: (1) keep as is; (2) a client can have **several named rates** (State 6.25%, City 2%) and a taxable line shows the combined tax as one number but stored per component; (3) separate rates for services vs products. I recommend (1) until you actually hit a case, since (2) and (3) change invoice layout and reports.

## 3. Rules I will follow whichever slices you pick
- Written examples above become tests (they are the acceptance criteria). Money stays integer cents; rounding half up away from zero; totals are sums of per-line integers.
- Nothing finalized is ever edited. Corrections are new documents (credit memo, refund, charge, void and reissue).
- Every new money record is audited, has RLS and an isolation test, and appears in the A/R and statement views.
- No automatic sending and no automatic money changes: a person approves fees, quantity updates and credit applications.
