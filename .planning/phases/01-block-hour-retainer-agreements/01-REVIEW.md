# Phase 1: Block-hour / retainer agreements — Review Summary

## Result: PASSED

**Cycles Used**: 1
**Reviewers**: testing-qa-verification-specialist, engineering-senior-developer, engineering-backend-architect, design-ux-researcher
**Evaluators**: code-quality, ui-ux, integration, business-logic
**Completed**: 2026-10-09

## Findings Summary
- Must-fix (blocker, critical, major) found: 0; fixed: 0; unresolved: 0
- Suggestions (minor, advisory): 0
- Deferred (confidence 50-79%): 17
- Hot spots (flagged by 2+ reviewers): `backend/app/billing.py`, `frontend/src/pages/billing/Rates.tsx`, `frontend/src/pages/billing/Agreements.tsx`, `frontend/src/Block.test.tsx`

## Findings Detail
(none)

## Reviewer Verdicts
- Cycle 1, testing-qa-verification-specialist: **NEEDS WORK**
- Cycle 1, engineering-senior-developer: **NEEDS WORK**
- Cycle 1, engineering-backend-architect: **NEEDS WORK**
- Cycle 1, design-ux-researcher: **NEEDS WORK**
- Cycle 1, evaluator:code-quality: **PASS**
- Cycle 1, evaluator:ui-ux: **NEEDS WORK**
- Cycle 1, evaluator:integration: **PASS**
- Cycle 1, evaluator:business-logic: **NEEDS WORK**

## Suggestions (Not Required)
(none)

## Deferred (Medium Confidence)
- `backend/app/billing.py` [major, 65%]: `_pull_block` dereferences `a = block_agreement_for(...)` without a None check. `add_unbilled` finds the block line through the line's `agreement_id` and `ag.type == "block"`, but `_pull_block` looks the agreement up again by date window. If the agreement is edited after the draft run invoice exists, `a` is None or has the wrong state. Two cases: `end_date` moved before the run month (None, so `a.block_minutes` raises AttributeError), and a block agreement whose `block_minutes` was cleared (`block_minutes_covered` stays `None * int`, TypeError in `block_included_minutes`). In `update_agreement`, `block_minutes` is cleared when the type leaves block, but the type check in `add_unbilled` rereads the agreement, so the first case is the realistic one.
- `backend/app/billing.py` [minor, 70%]: `_pull_agreements` recomputes the covered window (`first = max(a.start_date, start)`, `last = min(a.end_date, end) if a.end_date else end`). `proration_days` (lines 643-644) already does the same calculation, so the clamp logic is now written twice.
- `backend/app/billing.py` [minor, 55%]: `_validate_agreement` raises `Conflict` (409) for end date before start date. It raises the new `InvalidAgreement` (422) for the block-field checks. Both come from one validator, and the router's `AGREEMENT_ERR` documents 422 only for the new class.
- `backend/app/billing.py` [minor, 60%]: The block-line lookup in `add_unbilled` is a dense generator expression with a walrus operator and a `ctx.db.get` per line. It duplicates what `_pull_agreements` already tracks as `block_line`.
- `backend/app/billing.py` [major, 55%]: Releasing block draw-down is implemented separately in `delete_line` and in `_reset_block_consumption`, with different rules. `delete_line` zeroes `block_minutes_covered` only for entries linked to the deleted line. A partially covered entry sits on the overage time line, not the block line. Deleting the block "agreement" line therefore leaves that entry's covered minutes set. Deleting the overage line zeroes its covered minutes while the block line's "used" description still counts them.
- `backend/alembic/versions/0023_block_agreements.py` [minor, 60%]: The rule "at most one block agreement per client for any date" is enforced only in the service layer (`_check_block_overlap`, `billing.py` 250-267). It uses a `SELECT ... FOR UPDATE` on the organization row. The migration adds no database constraint for it, such as a GiST exclusion constraint on `(organization_id, daterange(start_date, end_date, '[]')) WHERE type = 'block'`. Other writers (seed scripts, direct SQL, a future code path that skips the service) can bypass the check. `block_agreement_for` (`billing_repo.py` 93-107) then silently picks the lowest id, so the other block's hours are never drawn down. The block-hours money rules require the one-block invariant.
- `backend/app/billing.py` [minor, 50%]: `update_agreement` lets a PATCH change `block_minutes`, `start_date`, `end_date` and `type` on a block agreement that already has finalized invoices. Nothing records or limits what that edit affects. Past invoice lines keep their old text, but the "included" figure for a later re-run of a draft run changes. Quantity changes get an `AgreementQuantityLog` entry. `block_minutes` changes get no equivalent log and no audit-diff reason.
- `frontend/src/pages/billing/Rates.tsx` [major, 70%]: The "Not covered by blocks" column uses an inverted double negative. A checked box means the work type is excluded (`checked={!w.block_covered}`). The column has no explanatory text. The page intro (line 21) and footnote (line 30) don't say what a block is, or that unchecked work types draw down block hours. The checkbox saves immediately on change, with no saved or pending indicator.
- `frontend/src/pages/billing/Agreements.tsx` [major, 75%]: The page's only explanatory text (line 32) describes per-user and per-device quantity and proration. It never says how Block hours behave. Row 95 shows only "(N h included)". Nothing in the UI shows hours used or remaining, or that unused hours expire at month end with no rollover and that overage is billed.
- `frontend/src/pages/billing/Agreements.tsx` [minor, 65%]: The `save`, `saveHours`, `end` and `adopt` buttons have no pending or disabled state. The `saveHours` button stays active while the request is in flight.
- `frontend/src/Block.test.tsx` [minor, 65%]: The tests do not cover several UI branches. These are: editing included hours on an existing row (Save visibility and the PATCH body); the zero or empty hours validation error; the read-only view for users without `billing:write`; and the Rates invalid-rate and disabled states.
- `frontend/src/pages/billing/Agreements.tsx` [major, 70%]: `hoursText` (and `qtyText` on line 62) are seeded from props once with `useState`. After a successful `saveHours` the list refetches, but the input is never resynced. If another user or tab changes `block_minutes`, the row keeps showing the stale hours. The Save button is also hidden or shown by comparing the stale text against fresh data.
- `frontend/src/pages/billing/Rates.tsx` [minor, 55%]: The taxable and block-covered checkboxes save immediately on change and are controlled by server data. They have no pending state and no optimistic update. If the PATCH fails, the error appears only in the shared ErrorMsg above the table, away from the row.
- `frontend/src/pages/billing/Agreements.tsx` [minor, 60%]: The hours inputs use `min={0}`, but validation rejects 0 (`!(h > 0)`). `a.block_minutes / 60` is displayed unformatted, so a value such as 100 minutes shows as 1.6666666666666667 h. The input shows the same long number, and `step={0.25}` flags it as invalid.
- `frontend/src/pages/billing/Agreements.tsx` [advisory, 50%]: The "end" action uses `window.prompt` for a date, with no validation of the format. The history panel is not a labelled region, so its expansion is not announced to assistive technology.
- `backend/app/billing.py` [minor, 50%]: The monthly run draws the block down only for entries dated inside the run month, and _pull_time bills everything else normally. test_prior_month_unbilled_time_bills_normally covers a month with no block. I found no test or doc statement for earlier-month covered-type time in a month that did have a block agreement but was never run. That time would bill at the full rate in a later run.
- `backend/app/ticket_services.py (called from backend/app/billing.py _pull_block, lines 676-707)` [major, 75%]: `_pull_block` records `block_minutes_covered` on a time entry that is only partly covered when the overage cannot be billed (no hourly rate). That entry keeps `invoice_line_id = NULL`, so it is not locked. `update_time` only checks `invoice_line_id`. It can change minutes, billable, work_date or work_type, and it never resets or clamps `block_minutes_covered`. If minutes drop below the stored covered value, the DB check `ck_time_entries_block_covered` (0 <= covered <= minutes_billable) fails and the user gets a 500. If the entry is instead moved to another month or work type, the stale covered minutes stay. Those minutes are then subtracted in `_pull_time` and are never billed. The same applies to entries at billable=false.

## Coverage
No coverage data found (looked for coverage/coverage-summary.json, coverage-summary.json, coverage/lcov.info, lcov.info, coverage.xml, coverage/cobertura-coverage.xml, coverage/coverage.xml, coverage.txt, coverage/coverage.txt). Advisory only: run the test suite with coverage to check review.coverage_thresholds.
