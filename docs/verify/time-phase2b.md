# Phase 2B verification: timesheet approval and payroll export

Approval is for payroll and records only. Billing runs ignore it completely.

1. As a tech, log some ticket and internal time this week. **My timesheet** shows a grey "open" pill and a **Submit week** button.
2. Start a timer, then try Submit: refused ("Stop or discard your running timer").
3. Stop the timer and **Submit week**. The pill turns "submitted"; the Void links and the internal-time form disappear. Try to log ticket time for that week from a ticket: refused ("locked").
4. Other weeks stay editable. You cannot move an entry into the locked week.
5. As an admin, **My timesheet** shows **Timesheet approvals** with the submitted week. Click **Return**, give a reason. The tech sees an amber "returned" banner with the reason, can edit again, and re-submits.
6. **Approve** the week. Even admins cannot edit it; **Return** works on an approved week too (reason required).
7. Choose a date range and click **Download hours CSV**. Rows are one per person, day and category (ticket time and each internal category), actual hours, approved weeks only. Returned or unsubmitted weeks, and voided time, are absent.
8. A tech and a billing user get 403 on approve, return, the queue and the CSV.
9. Audit log: `timesheet.submit/approve/return` and `report.export` (payroll-hours).
10. Billing: run billing as usual; time from unsubmitted or unapproved weeks is still billed.

Admins can approve their own week (audited).
Automated: `backend/tests/test_timesheet_approval.py`, `frontend/src/Phase2A.test.tsx`.
