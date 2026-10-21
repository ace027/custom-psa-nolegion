# Verify: Projects and project billing (Phase 8)

Run this once in Phase 14. Mark each item pass or fail with a note.

## Prerequisites
- Demo data is seeded (`python -m app.seed`): "Office network refresh" (fixed fee $2,500.00, Contoso Dental) and
  "Microsoft 365 migration" (T&M, $1,000.00 budget, Fabrikam Engineering, 5 h of Remote time).
- Sign in as admin (Ada). Remote has a rate set under Billing > Rates; Onsite is taxable in the demo data.
- Billing run steps need a client with a monthly agreement; the demo clients have one.

## Checks
- [ ] 1. Projects page: both demo projects are listed with client, status, mode, budget or fee, actual hours and
  remaining. The Client and Status filters narrow the list.
- [ ] 2. Create a project (name, client, dates, billing mode and fee or budget). Expect a draft project page. Sign in
  as a tech: the form has no billing fields. Sign in as read-only: no form and no write buttons anywhere.
- [ ] 3. Add two phases, then add tasks with an estimate, assignee and dates. Each task shows a ticket number linking
  to its ticket, and the ticket page shows "Project: <name>".
- [ ] 4. Make task B depend on task A: B shows "Blocked" until A is resolved. Then try to make A depend on B. Expect an
  inline error about a loop and no change.
- [ ] 5. Board tab: cards sit in New, Open, Waiting and Resolved by ticket status. Use the Move select on a card; the
  ticket's status changes (check the ticket page) and the Blocked badge follows the dependencies.
- [ ] 6. Log time on a task's ticket. Budget tab: actual hours, cost at rates and remaining update.
- [ ] 7. Approve a draft fixed-fee project (needs billing:write). Expect status Active and billing mode locked.
  Click "Bill fixed fee now": an invoice line for the fee appears and the page shows "Fixed fee billed" instead of the button.
- [ ] 8. Run the monthly billing run. Expect the fixed-fee project's time on the invoice as a $0 line marked covered
  by the fixed fee.
- [ ] 9. Take the T&M project over budget across two billing runs (log more time between runs). Expect the first run
  capped at the budget, a $0 over-budget line after that, and a red "Over budget" warning on the Budget tab with remaining $0.00.
- [ ] 10. Void an invoice from a project billing run, then re-run billing. Expect the time to be billed again once and
  the budget figures to match the live invoices.
- [ ] 11. Make a project taxable and log time on a taxable work type (Onsite in the demo). Expect tax on that
  invoice line at the client's rate; non-taxable work types carry no tax.
- [ ] 12. Client page: the Projects card lists the client's projects with status and remaining budget, linked.

## Assumptions to confirm
- Milestones (phase completion) are not billed: only the fixed fee on demand and time at rates are.
- Project time does not use block hours: it is never drawn from a client's support block agreement.
