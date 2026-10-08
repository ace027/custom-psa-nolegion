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
- Slice B (submit/approve/lock, payroll CSV): next.
- Slice C (expenses, mileage, receipts, billing): after B.
