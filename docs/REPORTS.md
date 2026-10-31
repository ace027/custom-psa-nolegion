# Reports and dashboards: metric dictionary (Phase 11)

Every rule here is an **assumption** until the owner confirms it in Phase 15 (see `docs/verify/reports.md`). All reports need `report:read` (admin and billing). Technicians see only their own "My week" tiles.

## Conventions
- Money is integer cents; the screen shows dollars, CSV files show dollars.
- A percentage is stored as integer basis points: `round_half_up(numerator * 10000 / denominator)`, and is **null** (shown as `-`) when the denominator is 0. The screen shows two decimals, for example `92.50% (n=40)`. n is the count the percentage was computed from.
- Durations are p50 and p90 using the nearest-rank method, shown as hours and minutes.
- Dates are business-time-zone dates. Range reports take `from` and `to` (default: this month on screen; the API default is the last 12 months).
- Each CSV download writes an audit row and uses the same query as the page.

## SLA performance
- **Definition**: how often tickets met their first-response and resolution targets.
- **Population and date basis**: tickets created in the range.
- **Formula**: met % = met / (met + breached), per clock. First response is met when `first_responded_at <= sla_first_response_due`, breached when it is later, or when it is empty and now is past the due time. Resolution uses `resolved_at` (or `closed_at` when empty) against `sla_resolution_due`.
- **Exclusions**: pending tickets (not responded, not yet due) and tickets with no due date are left out of the percentage and counted separately (Pending, no SLA).
- **Grain**: one row per priority, client or assignee (group selector) plus a total.
- **Durations**: business minutes with the SLA calendar; resolution minus paused minutes, floored at 0.
- **Rounding**: basis points; nearest-rank p50 and p90.
- **Reconciliation proved**: met + breached + pending + no SLA equals the ticket count in each row, and the rows add up to the total.

## Technician utilisation
- **Definition**: time worked against time available.
- **Population and date basis**: active technicians; time entries by work date in the range.
- **Formulas**: capacity = for each non-holiday date, the person's work-hours minutes for that weekday minus overlapping time off. Logged = non-voided ticket time (actual minutes) plus internal time. Billable = non-voided billable ticket time (actual minutes). Utilisation = logged / capacity; billable % = billable / capacity.
- **Automation time (owner decision 2026-10-30)**: entries with type `automation` are not in logged, billable or utilisation %. Their non-voided actual minutes are reported in a separate `automation_minutes` column (last column in the CSV), per technician and in the total.
- **Exclusions**: voided entries; holidays; time off.
- **Grain**: one row per technician plus a team total. n shown is capacity minutes.
- **Rounding**: basis points. A person with no capacity shows `-`.
- **Reconciliation proved**: total logged minutes equal the sum of the underlying time entries.

## Receivables aging
- **Definition**: open invoice balances by days past due.
- **Population and date basis**: finalized invoices with a balance, **as of the day it is run**. There is no range; the CSV and scheduled emails also ignore the period and say so.
- **Formula**: buckets Current, 1-30, 31-60, 61-90, 90+ by days past the due date; total open = sum of buckets; credit shown separately.
- **Exclusions**: void and fully paid invoices.
- **Grain**: one row per client plus a total.
- **Reconciliation proved**: the total equals the sum of all open invoice balances (the same figure as Billing > Receivables).

## Client profitability
- **Definition**: revenue less the cost of serving each client.
- **Revenue**: exactly the revenue report for the same range: finalized, non-void invoices and non-voided lines, excluding tax, by invoice date.
- **Cost**: labour + goods + expenses.
  - Labour per time entry = `round_cents(actual minutes * cost rate / 60)`, rounded per entry then summed, dated by work date. Cost rate is the hourly rate on the user (Users page, `user:manage`). Entries by someone with no rate count as $0 and are reported as **minutes without cost rate**.
  - Goods = delivered inventory items (quantity x unit cost, dated by delivery date), plus non-voided product charges in range that no inventory item covers, at quantity x product cost. Charges whose product has no cost are counted as **charges without cost**.
  - Expenses = expense amounts (the cost, not the marked-up price), dated by expense date.
- **Automation time (owner decision 2026-10-30)**: labour cost counts labour entries only; automation entries add no labour cost.
- **Margin** = revenue - cost. Margin % = margin / revenue, `-` when revenue is 0 or less.
- **Exclusions**: internal time is not attributed to clients.
- **Grain**: one row per client plus a total.
- **Reconciliation proved**: profitability revenue equals the revenue report for the same range.
- **Worked example**: 50 minutes at $90.00/h = round(50 x 9000 / 60) = 7500 cents = **$75.00 labour**. With $200.00 revenue and no other cost, margin is $125.00 and margin % is 62.50%.

## Dashboards
- **My week** (all staff, own data only): open tickets, SLA at risk and breached, appointments today, logged / billable / capacity this week and utilisation.
- **Business** (`report:read`): month-to-date revenue and margin, AR total with buckets, unbilled, SLA met over the last 30 days (today minus 29 days through today) with n, and team utilisation for last week (previous Monday to Sunday). Month to date runs from the 1st through today. Each tile links to its report.

## Scheduled reports
- A schedule names a report, a frequency and recipients. Weekly: a weekday; covers the previous Monday to Sunday. Monthly: a day 1-28; covers the previous calendar month. Aging is always "as of the run date".
- Recipients are staff users, never free-text addresses. Each must be active and hold `report:read` when the email is sent; saving a schedule with an ineligible recipient is refused (409 naming the user).
- The CSV is attached to an outbound email queued by the worker. One run per schedule and period (enforced by a unique key), so two workers cannot send twice.
- Failures and skips are recorded in the runs history and are **not retried** in the same period. Each send writes an audit row.
- Everyone with `report:read` can read schedules and runs; only `config:manage` can create or change them. Schedules are deactivated, not deleted.
