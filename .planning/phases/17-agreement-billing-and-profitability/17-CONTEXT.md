# Phase 17: Agreement billing and profitability -- Context

## Phase Goal
Every ticket and time entry is billed to an agreement, so utilisation and per-agreement profitability are true, including flat-fee all-you-can-eat clients.

## Requirements Covered
- Owner test note 8: tickets and time entries carry an agreement, defaulted from the client's active agreement and changeable by staff
- P01-01 note: flat-fee all-you-can-eat: all time attaches to the flat-fee agreement, nothing extra billed, profitability tracked
- Block-hour unused hours configurable per agreement: expire at period end, or roll over with an optional cap
- Profitability and utilisation reports break down by agreement, including flat-fee agreements

## What Already Exists (from prior phases)
- Agreement model (models.py ~887): types per_user, per_device, flat, block; block_minutes for block; no rollover fields
- Block hours: billing.py block_included_minutes (~657, per run month, prorated), allocate_block (~666), _pull_block (~679); TimeEntry.block_minutes_covered; billing_repo.block_candidates (~213) picks the org's labour time; voiding resets consumption (~1229)
- T&M time billing: billing.py _pull_time (~523), _bill_tm_time (~801); InvoiceLine.agreement_id exists
- Tickets (models.py ~607) and TimeEntry (~723) have no agreement_id; time is created in ticket_services.add_time (~451), update_time (~502), void_time (~549)
- Profitability: report_metrics.profitability (~397) groups by client only; labour cost = minutes_actual * users.cost_rate_cents/60; utilisation at ~260; routes routers/reports.py /utilisation, /profitability, /profitability.csv
- Migration head 0040 (test_seed_and_migrations.py:49)
- Phase 16 permissions: billing:read catalog, invoice:read finance, report:read reports; manager role

## Key Design Decisions
- ASSUMED (auto run, owner may revise): no billing behaviour changes until the owner opts in per agreement. New flags default to today's behaviour.
- Agreement.all_inclusive (bool, default false, only allowed true on type flat): time attached to an all-inclusive flat agreement is recorded and costed but never billed (excluded from T&M time and block consumption).
- Agreement.rollover (expire|roll, default expire) and rollover_cap_minutes (nullable, >0; null = no cap), only meaningful on block agreements; validation rejects them on other types.
- Rollover is computed, not stored: for run month M, carried_in(M) = 0 when expire; when roll, carried_in(M) = min(cap, carried_in(M-1) + included(M-1) - used(M-1)) floored at 0, walking months from the agreement start; used(M) counts only block_minutes_covered on entries in FINALIZED runs of month M; only months a finalized run billed this block on a live invoice accrue or use anything (corrected after build: counting unbilled months would carry hours from before the PSA was used). Carried minutes are consumed before the month's own included minutes; overage is billed exactly as today.
- tickets.agreement_id and time_entries.agreement_id: nullable FKs to agreements. Null means 'no agreement' and keeps today's behaviour exactly (T&M, and block consumption by any unattached labour time of the org, as today). No backfill of existing rows.
- Default on ticket create: the org's single active agreement (on the creation date) that is block or all-inclusive flat; if there are zero or several, null. A new time entry defaults to its ticket's agreement_id. Staff with ticket:write can change a ticket's agreement (applies to new time only) and an unbilled time entry's agreement; changing a billed entry (invoice_line_id set or block_minutes_covered > 0 in a finalized run) is a 409 Conflict. The chosen agreement must belong to the same org, else 422.
- Block allocation considers labour entries attached to that block agreement OR unattached (null); entries attached to another agreement are excluded. T&M bills unattached entries and entries attached to non-inclusive agreements, as today.
- Per-agreement profitability: revenue = invoice lines with that agreement_id plus T&M time lines for entries attached to it; labour cost = cost of time attached to it; unattached rows report under 'No agreement' so nothing is hidden. Reports stay behind report:read plus invoice:read (finance data, Phase 16).
- Verification inside plans uses targeted test files (the full backend suite takes 17-30 min and exceeds agent budgets); the orchestrator runs the full suite before pushing.
- Billing math plans run on the Opus coder (model: opus), per CLAUDE.md money rules.
- Board quick-assess: no red flags; recommendations taken: exact-cent seeded tests, a 'No agreement' bucket, internal-only reports. Architecture proposals: skipped (auto, no spec recommendation).

## Plan Structure
- **Plan 17-01 (Wave 1)**: Agreement on tickets and time entries -- Add the agreement link to tickets and time entries with defaulting and staff override, plus the new agreement settings fields, without changing what gets billed.
- **Plan 17-02 (Wave 2)**: Billing by agreement: all-inclusive and block rollover -- Make billing runs respect the attachment: no extra billing for time on all-inclusive flat agreements, block consumption by attached or unattached time, and configurable rollover of unused block minutes.
- **Plan 17-03 (Wave 2)**: Profitability and utilisation by agreement -- Add a by-agreement breakdown to the profitability and utilisation reports and CSV, with a 'No agreement' bucket.
- **Plan 17-04 (Wave 3)**: Agreement controls and reports in the UI -- Let staff see and change a ticket's and a time entry's agreement, let billing set all-inclusive and rollover on agreements, and show profitability and utilisation by agreement.
