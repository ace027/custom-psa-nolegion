# Phase 6: RMM alerts to tickets — Review Summary

## Result: PASSED

**Cycles Used**: 1
**Reviewers**: testing-qa-verification-specialist, engineering-senior-developer, design-ui-designer, design-ux-researcher
**Evaluators**: code-quality, ui-ux, integration, business-logic
**Completed**: 2026-10-20

## Findings Summary
- Must-fix (blocker, critical, major) found: 0; fixed: 0; unresolved: 0
- Suggestions (minor, advisory): 1
- Deferred (confidence 50-79%): 21
- Hot spots (flagged by 2+ reviewers): `backend/app/integrations/ninjaone.py`, `backend/app/rmm_alerts.py`, `backend/app/worker.py`, `frontend/src/pages/RmmAlertsCard.tsx`

## Findings Detail
| ID | Severity | Location | Issue | Reviewers | Confidence | Status |
|----|----------|----------|-------|-----------|------------|--------|
| F-001 | minor | `backend/app/rmm_alerts.py:20` | The module imports two underscore-private helpers from sibling modules. `_safe` comes from `app.asset_sync` (defined at asset_sync.py:245). `ticket_links._insert` (defined at ticket_links.py:97) is called directly. | engineering-senior-developer, evaluator:code-quality | 80% | deferred |

## Reviewer Verdicts
- Cycle 1, testing-qa-verification-specialist: **NEEDS WORK**
- Cycle 1, engineering-senior-developer: **NEEDS WORK**
- Cycle 1, design-ui-designer: **NEEDS WORK**
- Cycle 1, design-ux-researcher: **NEEDS WORK**
- Cycle 1, evaluator:code-quality: **NEEDS WORK**
- Cycle 1, evaluator:ui-ux: **NEEDS WORK**
- Cycle 1, evaluator:integration: **NEEDS WORK**
- Cycle 1, evaluator:business-logic: **NEEDS WORK**

## Suggestions (Not Required)
- F-001 `backend/app/rmm_alerts.py`: The module imports two underscore-private helpers from sibling modules. `_safe` comes from `app.asset_sync` (defined at asset_sync.py:245). `ticket_links._insert` (defined at ticket_links.py:97) is called directly. (fix: In `asset_sync.py` and `ticket_links.py`, expose public names (for example `safe_error` and `link_tickets`), or move `_safe` to a shared util. Import those names here. If `_insert` is deliberately the right entry point for system callers, say so in its docstring.)

## Deferred (Medium Confidence)
- `backend/app/integrations/ninjaone.py` [major, 60%]: `list_alerts` makes a single unpaginated `GET /v2/alerts` (the docstring says "UNVERIFIED"). `poll()` treats the returned list as the complete set of active alerts. Any alert missing from it is cleared, and under `always_resolve` or `resolve_if_untouched` its ticket is auto-resolved.
- `backend/app/rmm_alerts.py` [major, 55%]: The asset lookup joins `AssetSource` to `Asset` without filtering `Asset.retired_at IS NULL`. An alert on a device whose asset has been retired still creates a ticket linked to that retired asset. No test covers this.
- `backend/app/rmm_alerts.py` [minor, 55%]: `priority_for` falls through to `repo.get_default(...) or active[0]`. If there is no default priority and no active priority, this raises `IndexError`. The `or` expression is also evaluated eagerly only when the default is missing, so the failure appears only in that state.
- `backend/app/worker.py` [minor, 60%]: There is one outer try/except around the loop over all due integrations. If `poll` raises outside its internal handling (for example a DB error at flush, or `_safe` failing), the session is left in a failed state. There is no rollback, and the remaining integrations are skipped for that tick.
- `backend/app/rmm_alerts.py` [major, 55%]: Every open row whose condition is missing from the vendor response is cleared. Under the default `resolve_if_untouched` rule, its ticket is also auto-resolved. A 200 response with an empty or truncated list (for example a page-limited `/v2/alerts`) is treated as "all alerts cleared". `list_alerts` is one unpaginated GET, and its docstring marks it UNVERIFIED.
- `backend/app/rmm_alerts.py, backend/app/integration_services.py` [advisory, 50%]: `integration_services` imports `CLEAR_RULES` and `settings` from `rmm_alerts`. `rmm_alerts` is a worker and domain module that also imports `ticket_services`, `registry` and `asset_sync`. This couples the service and API layer to the polling module, which raises the risk of circular imports. The alert config keys and defaults are also defined in `rmm_alerts` but validated in `integration_services`.
- `frontend/src/pages/RmmAlertsCard.tsx` [major, 50%]: The "Create tickets from alerts" checkbox is nested in a `<label>` as a bare `<input>`. The label text is associated, but the checkbox has no `focus-visible` styling. Separately, the Field-wrapped inputs may not have a programmatic label. Check that `Field` uses `<label>` wrapping, because the select and number input rely on it.
- `frontend/src/pages/RmmAlertsCard.tsx` [minor, 75%]: Only the first `th` and `td` (Severity) get `p-1`. The other eight columns have no padding, so adjacent columns (Client, Device, Message, Times, dates) run together. The `th` elements have no `scope="col"`. The table has no caption or accessible name.
- `frontend/src/pages/RmmAlertsCard.tsx` [minor, 65%]: Save and "Check now" give no success feedback. The "Check queued" and "Last checked" status text is not in a live region. Save errors appear below the status block, away from the buttons. "Check now" is disabled when alerts are not enabled in the saved config, with no explanation, so the button looks broken after the user ticks the checkbox but before saving.
- `frontend/src/pages/RmmAlertsCard.tsx` [minor, 50%]: Badge colors (`text-orange-800` on `bg-orange-100`, `text-amber-800` on `bg-amber-100`) are probably around 6:1 or better and pass AA. The badge text is 12px, `text-xs` with no padding on the y-axis (`px-1.5` only). The links use `text-blue-700` on a white background, which passes.
- `frontend/src/pages/RmmAlertsCard.tsx` [minor, 70%]: Saving the alert settings gives no success feedback. `save` has only `onSuccess: onSaved`, which refetches the list. The button label stays "Save alert settings" and nothing says the change was stored. The `alertsOn` flag, which enables "Check now", comes from the saved config. So the user ticks "Create tickets from alerts" and sees "Check now" stay disabled until the refetch finishes, with no explanation.
- `backend/app/integrations/ninjaone.py` [major, 60%]: The NinjaOne alert field names and the endpoint shape are explicitly labelled UNVERIFIED in the code (uid, deviceId, sourceConfigUid, sourceType, severity, createTime). Tests only use fakes built from the same assumptions. `condition_key` is built as `device:sourceConfigUid or sourceType or uid`. If neither source field exists, the key falls back to `uid`, which changes on every occurrence, so dedupe silently stops working.
- `backend/tests/test_rmm_alerts.py` [minor, 50%]: Several branches in `poll` have no test. An unknown `alert_clear_rule` in stored config should fall back to the default. A failure inside `_clear` should roll back the counters. An open alert dropped below the minimum severity should be handled. A same-uid alert whose ticket was resolved by a technician should not create a new ticket. `resolve_by_system` and `system_note` are not tested directly.
- `frontend/src/pages/RmmAlertsCard.tsx` [advisory, 50%]: The minutes input uses `min` and `max` and `required`, but the form has no custom validation message. An empty or non-integer value is accepted by `Number(minutes)` (for example "2.5").
- `backend/app/integration_services.py` [minor, 50%]: `list_alerts` loads every `Organization` row to map names. It also reads `a.ticket` and `a.asset` per row, which may be N+1 depending on the relationship loader. The `ticket` relationship is not verified in the viewed code.
- `frontend/src/pages/TicketDetail.tsx` [minor, 55%]: The asset name links to `/organizations/${t.organization_id}`, not to the asset.
- `backend/tests/test_vendor_adapters.py` [advisory, 50%]: I did not confirm that the `_to_alert` mapping has edge-case tests. The cases are: a missing `sourceConfigUid` falling back to `sourceType` or `uid`, an unknown severity, and a non-list body. Only the count of matches was checked.
- `backend/app/rmm_alerts.py` [major, 60%]: Open alert rows are only cleared inside `poll()`, and `due()` skips an integration when `alerts_enabled` is turned off, when the integration is disabled, or when its credentials are removed. Open `rmm_alerts` rows and their tickets then stay open indefinitely. They are not cleared or noted when polling is switched back on. The next poll clears everything that went quiet in between, and the rule applied is whatever is configured at that time.
- `backend/app/rmm_alerts.py` [major, 50%]: Any successful response from `list_alerts` is treated as the complete set of active alerts. The response is an unverified, unpaginated `GET /v2/alerts`, so a truncated, filtered or empty (but HTTP 200) response makes every open row "gone". Those rows are cleared and, under the default rule, their tickets are auto-resolved.
- `backend/app/rmm_alerts.py` [minor, 60%]: The ticket description uses `alert.created_at or now` as "First seen", but the `RmmAlert.first_seen_at` column is always set to `now`. The two values disagree for any alert that fired before its first poll.
- `backend/app/rmm_alerts.py` [minor, 50%]: `_untouched` treats a ticket as untouched unless it has an assignee, a human note or a time entry. A ticket where a technician only changed the status (for example, to pending or waiting) or another field still counts as untouched. The default rule will then resolve it behind the technician's back. The module docstring promises that a touched ticket is never resolved.

## Fixes Applied
- minor findings: engineering-backend-architect on F-001, F-001, F-002, F-003, F-004, F-006 (partial); engineering-frontend-developer on F-008, F-009 (done); left as is: F-001 [minor] private helper imports: not fixed. Exposing public names needs edits to asset_sync.py and ticket_links.py, which are not in my writable list. / F-001 [major] unpaginated list_alerts: not fixed. I can't verify how the NinjaOne /v2/alerts endpoint pages, and a safety valve (skip clearing on an empty result, or require two empty polls) is a design decision for the owner. / F-006 [major] truncated response mass-clears and resolves tickets: not fixed, for the same reasons as the F-001 major. Both findings need the same owner decision. / F-008 (labels): not changed. In /home/user/custom-psa-nolegion/frontend/src/ui.tsx, `Field` renders `<label className="block text-sm"><span>{label}</span>{children}</label>`, so the select and number inputs already have accessible names. / F-008 (checkbox focus-visible): not changed. The checkbox is a native input inside a label, so it keeps the browser's default focus ring. Adding custom styling would be a design choice.; checks 14/14 passed, 4 file(s) changed

## Coverage
No coverage data found (looked for coverage/coverage-summary.json, coverage-summary.json, coverage/lcov.info, lcov.info, coverage.xml, coverage/cobertura-coverage.xml, coverage/coverage.xml, coverage.txt, coverage/coverage.txt). Advisory only: run the test suite with coverage to check review.coverage_thresholds.

## Security Review

**Verdict**: PASS — 0 unresolved CRITICAL/HIGH finding(s). Details: `SECURITY-REVIEW.md`.

## Owner decisions and follow-up fixes (after review)
- Mass clear (review major findings, SEC MEDIUM): an alert clears only after 2 polls in a row without it (rmm_alerts.missed_polls, added to 0027). An empty list while alerts are open needs 3 empty polls in a row and shows a warning on the card. Audited as integration.alerts_suspicious.
- Flood cap (SEC MEDIUM): at most 25 new tickets per poll, with the rest deferred and shown on the card. condition_key and device id are capped at 200 chars (digest suffix), and the message bound is re-applied in the engine.
- Portal (SEC LOW): portal contacts see "Monitoring alert on <device>" instead of the stored description of RMM tickets.
- Minor fixes:
  - Audit failed or suspicious polls only when the error text changes.
  - Strip Cc/Cf/Zl/Zp characters from alert text.
  - Reject unknown alert* config keys.
  - Make the due() poll interval defensive, and raise Conflict when no priority exists.
  - Skip ignored client maps.
  - Remove the N+1 in list_alerts.
  - Make the helper names public (asset_sync.safe_error, ticket_links.link_related).
  - Add a two-integration colliding-device-id test.
- Still open by owner choice: SEC base_url allowlist (LOW), the INFO items.
