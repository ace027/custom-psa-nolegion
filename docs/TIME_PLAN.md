# Phase 2: time, expenses and timesheets

Status: **decisions made (section 4); building in slices A to C.** Part of [PARITY_ROADMAP.md](PARITY_ROADMAP.md).

## 1. What exists today (verified in code)
- Time entries are always on a ticket (so on a client): actual minutes, billable minutes rounded UP to the billing increment when logged, billable flag, void-not-delete, locked once on an invoice. Techs edit or void their own; admins anyone's.
- Billing pulls every unvoided, billable, uninvoiced time entry up to the run's end date. Product charges are billed the same way (`invoice_line_id` marks them as billed; voiding an invoice releases them).
- No timers, no weekly view, no approval, no expenses, no non-ticket time.

## 2. Scope, in slices (each ends tested, documented and pushed)
**A. Timers and internal time.** One start/stop timer per tech, on a ticket or on an internal category; stopping creates a normal time entry. Internal time (Administration, Training, Meeting, Paid time off; editable list) for work that belongs to no client; never billable. A weekly timesheet view that shows ticket and internal time together.
**B. Timesheet approval and payroll export.** A tech submits a week; an admin approves or sends it back with a reason; a submitted or approved week is locked against edits. CSV export of approved hours (and, after C, reimbursable expenses) for a date range.
**C. Expenses.** Expense and mileage entries with receipt uploads. Each can be reimbursable to the tech and/or billable to a client (at cost plus an optional markup, as a normal invoice line). Mileage uses a per-mile rate from Settings.

## 3. Rules I will follow
- Money stays integer cents; markup in basis points; ties round half up (same rule as invoices). Mileage is stored as miles (two decimals) and the rate in cents per mile; the amount is fixed when the expense is entered, so changing the rate later never rewrites old expenses.
- Nothing is deleted: time, internal time and expenses are voided with an audit row.
- Billing math for existing time and charges is **not changed**. Approval does not gate billing (decision 1).
- New client-owned tables carry `organization_id`, forced RLS and isolation tests; every endpoint documented and tested; every change audited; no new dependencies.
- Internal time and timers live in their own tables, so the billing-critical `time_entries` table and its rules are untouched.

## 4. Decisions (from you)
1. **Approval is for payroll and records only.** Billing runs behave exactly as today.
2. **Expenses are both reimbursable and billable to a client.**
3. **Internal (non-ticket) time is included.**
4. **Extras included:** start/stop timers, mileage, receipt uploads, CSV export for payroll.

## 5. Choices I made that you can veto
- Only admins approve timesheets (a one-person-admin shop can approve their own; it is audited).
- A week is Monday to Sunday.
- One running timer per tech. Starting another while one runs is refused (stop or discard first), rather than silently stopping the first.
- A timer left running past 24 hours cannot be saved automatically; it must be discarded and the time entered by hand.

## 6. Progress
- **Slice A (timers, internal time, weekly timesheet): built.** Migration 0017; see [verify/time-phase2a.md](verify/time-phase2a.md).
- **Slice B (submit/approve/return, edit lock, payroll CSV): built.** Migration 0018; see [verify/time-phase2b.md](verify/time-phase2b.md). A returned or never-submitted week is editable; a submitted or approved week is locked for everyone including admins (return it first). Reimbursable expenses join the CSV in slice C.
- **Slice C (expenses, mileage, receipts, billing, reimbursement CSV): built.** Migration 0019; design in section 7; see [verify/time-phase2c.md](verify/time-phase2c.md). **Phase 2 is complete and waiting for your review.**

## 7. Slice C design: expenses (money paths, agreed before coding)

**What an expense is.** One row per receipt or trip: date, who incurred it, a category (editable list), a description, an amount, and flags *reimbursable* (we owe the person), *billable* (we charge a client), *taxable*, an optional client and ticket, and any receipts. Mileage is an expense whose amount is computed: `miles × rate`.

**Amounts (integer cents, half-up away from zero, same as invoices).**
- Mileage: `amount = round_half_up(miles × cents_per_mile)`; miles has 2 decimals; the rate (whole cents per mile, in Settings, default 0 so it must be set first) is copied onto the expense, so changing the rate never rewrites old trips. Examples at 67 c/mile: 37.50 mi = 2,512.5 → **2,513 c** ($25.13); 12.35 mi = 827.45 → **827 c**; 0.50 mi = 33.5 → **34 c**.
- Reimbursement to the person is always the **cost** (`amount`), never the marked-up price.

**Billing an expense to a client.** It becomes an ordinary **product** invoice line (quantity 1), so every existing rule applies unchanged (frozen on finalize, released when the invoice is voided, tax per line on the rounded amount, shown on the client's invoice and statement). No new line kind, no change to the table constraint.
- `price = amount + round_half_up(amount × markup_bp / 10000)`; the line's unit price is `price`, amount = `price`.
- Tax: `round_half_up(price × client_tax_bp / 10000)` when the expense is taxable, else 0.
- Worked example: cost 12,345 c ($123.45), markup 1,500 bp (15%), taxable, client tax 825 bp (8.25%). Markup = 1,851.75 → 1,852. Price = **14,197 c**. Tax = 14,197 × 0.0825 = 1,171.2525 → **1,171 c**. Line total **15,368 c** ($153.68). The person is reimbursed **12,345 c**.
- Mileage billed at cost with no markup: 2,513 c line; tax 0 if not taxable.
- Pulled by the same invoice generation as time and charges: unvoided, billable, not already on an invoice, dated on or before the run's end date. Approval does **not** gate it (decision 1). A billable expense must have a client.
- Locked once on an invoice (cannot be edited or voided); voiding the invoice releases it, like time and charges.
- The unbilled report includes unbilled expenses at their billed price (separate column).

**Locking by timesheet.** An expense dated in a submitted or approved week of its owner cannot be added, edited or voided (return the week first). Submitting a week with only expenses is allowed.

**Receipts.** Uploaded as the raw request body (no new dependency), PDF/PNG/JPEG/WebP, max 10 MB each, stored on disk under the attachments directory with a content hash, always downloaded as an attachment. Owner or admin only. A receipt on a billable expense is internal; clients never see it.

**Payroll CSV.** The existing hours export gains a second file: reimbursable expenses (cost amount, category, description, mileage) for **approved** weeks in a date range. Billable-only expenses are not reimbursed and are not in it.

**Not building (BACKLOG):** marking expenses "reimbursed"/paid, per-category GL codes, receipt OCR.
