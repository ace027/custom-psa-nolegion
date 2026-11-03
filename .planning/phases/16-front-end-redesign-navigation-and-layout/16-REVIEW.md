# Phase 16: Front-end redesign (navigation and layout) — Review Summary

## Result: PASSED

**Cycles Used**: 2
**Reviewers**: testing-qa-verification-specialist, engineering-backend-architect, engineering-senior-developer, design-ui-designer
**Evaluators**: code-quality, ui-ux, integration, business-logic
**Completed**: 2026-11-02

## Findings Summary
- Must-fix (blocker, critical, major) found: 5; fixed: 5; unresolved: 0
- Suggestions (minor, advisory): 1
- Deferred (confidence 50-79%): 17
- Hot spots (flagged by 2+ reviewers): `frontend/src/nav/useBookmarks.ts`, `frontend/src/nav/Rail.tsx`, `frontend/src/nav/AllPages.tsx`, `frontend/src/App.tsx`

## Findings Detail
| ID | Severity | Location | Issue | Reviewers | Confidence | Status |
|----|----------|----------|-------|-----------|------------|--------|
| F-001 | critical | `frontend/src/App.tsx:277` | `<Route path="users" element={<Users />} />` has no permission guard, unlike its sibling routes. `AdminLayout` also has no `can(...)` check. Every staff role holds `user:read`, so the API list endpoint answers them. | evaluator:code-quality, evaluator:integration, evaluator:business-logic | 80% | fixed |
| F-002 | major | `backend/app/ticket_services.py (the same gap is in /home/user/custom-psa-nolegion/frontend/src/scheduling/api.ts:172, /home/user/custom-psa-nolegion/frontend/src/lookups.ts:22, /home/user/custom-psa-nolegion/frontend/src/pages/crm/Leads.tsx:116 and /home/user/custom-psa-nolegion/frontend/src/pages/crm/OpportunityPage.tsx:117):30` | The backend now allows `manager` as an assignable and bookable role (`ASSIGNABLE_ROLES` here, `BOOKABLE_ROLES` in `scheduling.py:36`). The frontend technician and assignee pickers still filter on `role === "admin" // role === "tech"`, so managers never appear in them. | evaluator:code-quality | 80% | fixed |
| F-003 | major | `frontend/src/Navigation.test.tsx:79-130` | The navigation tests check what is listed for each role, and that admin can open every route. No test checks that a role without the permission is refused when it opens a restricted URL directly, such as `/admin/users`, `/billing/invoices`, `/procurement`, `/reports/sla`, `/admin/settings/mail` for a manager, or `/audit`. | evaluator:code-quality | 85% | fixed |
| F-004 | critical | `frontend/src/App.tsx:213-229` | The whole `/billing` route tree is guarded by `billing:read`, which the catalog split left on every staff role (tech, read_only, manager). The invoice-backed pages (runs, invoices, receivables, reminders, payments, credit-memos, late-fees) are routed on that permission. Nav items for these pages use `invoice:read`, but the routes do not. The `/billing` index redirects to `runs`. | evaluator:integration, evaluator:business-logic | 85% | fixed |
| F-005 | major | `backend/app/routers/config.py, backend/app/routers/ticket_config.py, frontend/src/pages/admin/settings/TicketSettings.tsx:57-63` | The Tickets settings page is gated by `service:configure` and renders the Ticket types, Custom fields and Canned responses cards. The API writes for ticket-types, canned-responses and custom-fields still require `config:manage`. Only queues, categories, priorities and work-types moved to `service:configure`. Statuses and holidays did move. | evaluator:integration | 80% | fixed |
| F-006 | advisory | `frontend/src/App.tsx:213-215` | F-001, F-004 and F-005 are fixed, so these are re-check results and not defects. F-001: `users` is now guarded by `user:manage` (line 281), and only admin holds that permission. F-004: the invoice-backed routes are nested under `can(me, "invoice:read")` (lines 216-228), and `reports` needs `report:read` and `invoice:read`. F-005: `TicketSettings.tsx` shows the Ticket types and Canned responses cards only with `config:manage` (lines 10, 19-20). The Custom fields editor sits inside the ticket-types card, so it is gated the same way. The remaining sections match their `service:configure` writes in `config.py` and `ticket_config.py`. | evaluator:integration | 80% | deferred |

## Reviewer Verdicts
- Cycle 1, testing-qa-verification-specialist: **PASS**
- Cycle 1, engineering-backend-architect: **PASS**
- Cycle 1, engineering-senior-developer: **PASS**
- Cycle 1, design-ui-designer: **NEEDS WORK**
- Cycle 1, evaluator:code-quality: **NEEDS WORK**
- Cycle 1, evaluator:ui-ux: **NEEDS WORK**
- Cycle 1, evaluator:integration: **NEEDS WORK**
- Cycle 1, evaluator:business-logic: **NEEDS WORK**
- Cycle 2, testing-qa-verification-specialist: **PASS**
- Cycle 2, engineering-backend-architect: **PASS**
- Cycle 2, engineering-senior-developer: **PASS**
- Cycle 2, design-ui-designer: **PASS**
- Cycle 2, evaluator:code-quality: **PASS**
- Cycle 2, evaluator:integration: **PASS**

## Suggestions (Not Required)
- F-006 `frontend/src/App.tsx`: F-001, F-004 and F-005 are fixed, so these are re-check results and not defects. F-001: `users` is now guarded by `user:manage` (line 281), and only admin holds that permission. F-004: the invoice-backed routes are nested under `can(me, "invoice:read")` (lines 216-228), and `reports` needs `report:read` and `invoice:read`. F-005: `TicketSettings.tsx` shows the Ticket types and Canned responses cards only with `config:manage` (lines 10, 19-20). The Custom fields editor sits inside the ticket-types card, so it is gated the same way. The remaining sections match their `service:configure` writes in `config.py` and `ticket_config.py`. (fix: None needed. Optionally add a `Navigation.test.tsx` case that a tech gets redirected from `/billing/invoices` and `/admin/users`.)

## Deferred (Medium Confidence)
- `frontend/src/nav/useBookmarks.ts` [minor, 70%]: While the GET `/me/bookmarks` query is still pending, `saved` is `[]`. The "Bookmark this page" button in the header (App.tsx 139) is already clickable then. A click on a slow connection runs `toggle`, which saves `[currentId]`. That PUT replaces the user's whole server-side list with one id. Example: a user with 6 saved bookmarks opens a page, clicks the star before the GET returns, and ends up with only that one page. The server list is overwritten with no undo.
- `frontend/src/nav/useBookmarks.ts` [minor, 50%]: Each change fires its own PUT with no ordering. Two quick moves (for example Alt+Down twice) put two requests in flight. If they reach the server out of order, the server keeps the older order. The mutation never refetches or invalidates on settle, so the cache keeps showing the newer optimistic order. The two disagree until a window-focus refetch or a reload, when the rail jumps to the stale order. The file's `shortcut:` comment only covers rollback after a failure, not this case.
- `backend/app/routers/auth.py` [advisory, 50%]: PUT /me/bookmarks accepts any well-formed page ids, so a stale or wrong id such as "retired-page" is saved without complaint. The schema comment says the server checks only the shape of the ids. The front end has to drop unknown ids on read.
- `backend/app/schemas.py` [advisory, 55%]: The bookmark limit of 8 is a bare literal in `schemas.py`. The same number is `MAX_BOOKMARKS` in `useBookmarks.ts` and is repeated in the route summary text in `routers/auth.py` line 206. Nothing ties these together.
- `frontend/src/nav/Rail.tsx` [major, 75%]: The Profile link and the ThemeToggle both carry `hidden md:…`, so they disappear below 768px. `/profile` is not an item in navConfig.ts, so All pages and the command palette don't list it either. On a phone, or a tablet narrower than 768px, nothing in the navigation leads to Profile, which holds the notification settings. There is also no way to switch theme.
- `frontend/src/nav/AllPages.tsx` [minor, 65%]: Small text and the unbookmarked star icon use `text-slate-400` on the surface background. That is about 2.6:1 on white, below the WCAG AA 4.5:1 for text and 3:1 for icons. The affected items are the section headings (`text-xs`), the palette group headings, the "Star pages to bookmark them" hint at 10.5px, and the unpressed star button.
- `frontend/src/nav/Rail.tsx` [minor, 60%]: The Profile link and the theme toggle carry `hidden md:flex` and `hidden md:block`. Below 768px the bottom tab bar has no route to `/profile`, which holds notification settings, and `/profile` is not in `NAV_ITEMS` or the palette.
- `frontend/src/nav/useBookmarks.ts` [minor, 60%]: `toggle` checks the 8-item cap against `saved`, which includes ids that are hidden (role changed or page retired). The person sees fewer than 8 bookmarks but is told "up to 8, remove one first". The hidden ids cannot be removed through the UI.
- `frontend/src/nav/AllPages.tsx` [minor, 55%]: The panel is a non-modal fixed overlay with no focus containment and no backdrop or outside-click close. Its document-level Escape handler also fires while the command palette is open, so Escape closes both and moves focus to the All pages button.
- `frontend/src/nav/AllPages.tsx (also /home/user/custom-psa-nolegion/frontend/src/nav/CommandPalette.tsx)` [minor, 75%]: Section headings use `text-xs uppercase text-slate-400`. The unbookmarked star icon button uses `text-slate-400`. The palette group headings use `text-slate-400`. All sit on a white or surface background at about 2.5:1 contrast. The rail empty-state hint (Rail.tsx 133) has the same problem.
- `frontend/src/nav/Rail.tsx` [major, 70%]: Below 768px the profile link and the ThemeToggle are `hidden`. `/profile` does not appear in navConfig (grep found no match), so it is not in All pages either. The header has no profile link. On a phone, a person cannot reach their profile and notification settings or change the theme.
- `frontend/src/nav/Rail.tsx` [minor, 60%]: On phones the rail shows only `index < 4` bookmarks, and the rest are `hidden`. The cap is 8. Bookmarks 5 to 8 cannot be reached from the bar, and they also cannot be reordered or removed from it.
- `frontend/src/nav/CommandPalette.tsx` [minor, 55%]: `aria-expanded` is hard-coded to "true". Group headings are `role="presentation"` inside a `listbox`, so screen readers do not announce groups. The "No matches" `<p>` has no live region. The `role="status"` region at line 209 only carries bookmark messages.
- `frontend/src/Navigation.test.tsx, Bookmarks.test.tsx, CommandPalette.test.tsx` [advisory, 50%]: I did not open the test files, the backend files or the settings pages. This review covered only the nav components and the App.tsx shell. No evaluation was done at 1280px or tablet widths with rendered output, and the contents of the other listed files were not checked in any pass.
- `backend/app/routers/reports.py` [minor, 60%]: Creating and updating report schedules requires `config:manage`. The Report schedules nav item and `/reports/schedules` route are open to anyone with `report:read`, including managers.
- `frontend/src/App.tsx` [minor, 50%]: The `reports` route redirects to `/billing` when the role lacks `report:read` or `invoice:read`. Technicians and read-only users hold `billing:read` but not `invoice:read`. They are sent to `/billing`, and the index then forwards them to the first visible billing item. The redirect works, but it goes through two hops. If a role ever had no visible `/billing/` item, the `/billing` index would send it to `/billing/agreements`, a page it may not be allowed to use.
- `frontend/src/pages/reports/ReportSchedules.tsx` [minor, 50%]: `holdsReportRead` is `u.is_active && (u.role === "admin" || u.role === "billing")`. This is the same role-literal pattern F-002 was about. A manager holds `report:read` and is shown "Report schedules" in navigation (Navigation.test.tsx line 31), but this check leaves managers off the list. The file is outside the evaluated set, so this is reported at low confidence. I did not read how the helper is used.

## Fixes Applied
- cycle 1: engineering-frontend-developer on F-001, F-002, F-003, F-004, F-005 (partial); checks 11/16 passed
- minor findings: engineering-frontend-developer on F-006, F-005, F-006, F-007 (done); engineering-backend-architect on F-001, F-002, F-003, F-004 (done); left as is: F-005 suggestion to add Profile to navConfig.ts and the palette: not done. navConfig.ts is not in my writable list, and a nav item is a small design decision. I put the link in the All pages panel instead. / F-006 (contrast): palette group headings are not fixed. They live in CommandPalette, which is not in my writable list. I did not check how the dark theme remaps the slate tokens. / F-006 (advisory re-check): no change needed. The optional Navigation.test.tsx case is not added. / F-001 (disabled star button): not done. App.tsx is not in my writable list. The data-loss risk is closed by the early returns in the hook, so a click during loading does nothing. The button just doesn't look disabled. / F-003: not changed. The advisory says no change is needed if the front end drops unknown ids. `items` in useBookmarks.ts does this through `navItem` and `canOpen`.; checks failed (5/16), changes undone

## Cycle Delta
- cycle 1: 5 must-fix, 0 suggestions, 15 deferred, 0 dropped (low confidence)
- cycle 2: 1 out-of-domain finding(s) filtered (engineering-senior-developer on backend, owner engineering-backend-architect); see .planning/logs/authority-decisions-2026-11-03.log
- cycle 2: 0 must-fix (resolved 5, new 0, unchanged 0), 1 suggestions, 2 deferred, 0 dropped (low confidence)

## Coverage
No coverage data found (looked for coverage/coverage-summary.json, coverage-summary.json, coverage/lcov.info, lcov.info, coverage.xml, coverage/cobertura-coverage.xml, coverage/coverage.xml, coverage.txt, coverage/coverage.txt). Advisory only: run the test suite with coverage to check review.coverage_thresholds.
