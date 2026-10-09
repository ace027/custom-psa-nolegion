# Phase 1: Block-hour / retainer agreements -- Context

## Phase Goal
Agreements can carry prepaid block hours that billable time draws down, with unused hours expiring at month end and overage billed at the normal rate, per approved money rules.

## Requirements Covered
- REQ-01

## What Already Exists (from prior phases)
- Billing (docs/BILLING.md): agreements flat/per_user/per_device (models.py:557-570, ck_agreements_type in 0003_billing.py:84), monthly runs create_run (billing.py:866-918) calling _pull_agreements (541-577, with Phase 3A calendar-day proration lines kind 'proration') and _pull_time (448-483, groups by ticket+work type, links each TimeEntry.invoice_line_id)
- hourly_rate with org overrides (billing.py:175-177, billing_repo.get_org_rate), money.round_cents ROUND_HALF_UP, integer cents, tax snapshot per line
- TimeEntry.minutes_billable is already rounded up to Settings.billing_increment_minutes (default 15); void releases links via _release (billing.py:714-729)
- Head migration 0022_late_fees.py; constraint changes use drop_constraint + create_check_constraint (0020_proration.py:13-16)
- Tests on real PostgreSQL psa_test with fixtures in backend/tests/conftest.py; test_zz_api_contract.py needs every route documented, permissioned and tested

## Key Design Decisions
- New agreement type 'block': fixed monthly price (unit_price_cents, quantity forced to 1) including agreements.block_minutes (positive multiple of billing_increment_minutes); price bills every month regardless of use
- Unused hours expire at month end; no ledger, consumption recomputed per run month
- Coverage: all billable time of the client with work_date inside the run month, except work types with block_covered = false (UI label 'Not covered by blocks'); earlier-month carry-over unbilled time bills normally
- Consumption order: work_date, then time entry id
- Straddling entry is split by minutes: time_entries.block_minutes_covered records the covered part; fully covered entries link invoice_line_id to the block agreement line; a straddling entry links to its overage time line and only its uncovered minutes count toward that line's quantity
- Overage bills as ordinary 'time' lines (grouped by ticket + work type, hourly_rate with overrides, work type taxability) for the uncovered minutes
- Mid-month start/end: price uses the existing proration credit line; included minutes are prorated by the same calendar days (block_minutes x covered_days / days_in_month) rounded DOWN to the billing increment
- At most one active block agreement per client for overlapping dates (409 Conflict otherwise)
- Only the monthly run consumes blocks; ad-hoc invoices (create_invoice include_unbilled) skip covered-type time whose work_date falls in a month overlapping the client's block agreement, leaving it for the run
- Void releases block links and resets block_minutes_covered to 0
- One tax rate per client stays; docs/BILLING_PLAN.md section E is updated to record that, superseding its earlier 'services vs products' note
- Architecture proposals: skipped by user
- Money/migration plans run on Opus per CLAUDE.md

## Plan Structure
- **Plan 01-01 (Wave 1)**: Block agreement schema, validation and money rules -- Add the block agreement type and supporting columns, validate block agreements (one active per client), expose the new fields in the API, and write the approved money rules into the billing docs.
- **Plan 01-02 (Wave 2)**: Billing-run block consumption -- Make the monthly billing run consume block hours in work-date order, split straddling entries by minutes, bill overage at normal rates, prorate included hours, release on void, and keep ad-hoc invoices from consuming blocks.
- **Plan 01-03 (Wave 2)**: Block agreements UI, seed and verify checklist -- Let billing users create and edit block agreements and mark work types 'Not covered by blocks', seed a demo block client, and add the manual verify checklist.
