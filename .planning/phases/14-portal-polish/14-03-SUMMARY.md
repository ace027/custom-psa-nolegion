# Plan 14-03 Summary: Portal polish frontend and manual checks

## Result
**Status**: Partial
**Wave**: 3
**Agent**: engineering-frontend-developer
**Completed**: 2026-10-31

## Agent Selection Rationale

| Candidate | Semantic | Heuristic | Memory | Total | Source |
|-----------|----------|-----------|--------|-------|--------|
| engineering-frontend-developer | — | 7 | 3.08 | 10.08 | mandatory |
| engineering-senior-developer | — | 17 | 2.91 | 19.91 | heuristic |
| testing-qa-verification-specialist | — | 12 | 3.15 | 15.15 | heuristic |

- **Task type detected**: implementation
- **Confidence**: LOW
- **Adapter**: claude-code
- **Model tier**: sonnet

## Completed Tasks
- [x] Task 1: Portal sign-in and My details (done)
- [x] Task 2: Attachments and export UI, staff fields (done)
- [x] Task 3: Tests and manual checks (done)

## Files Modified
- `README.md`
- `docs/verify/portal-polish.md`
- `frontend/src/PortalPolish.test.tsx`
- `frontend/src/api.ts`
- `frontend/src/pages/OrganizationDetail.tsx`
- `frontend/src/pages/TicketDetail.tsx`
- `frontend/src/portal/ExportButton.tsx`
- `frontend/src/portal/MyDetailsPage.tsx`
- `frontend/src/portal/PortalApp.tsx`
- `frontend/src/portal/PortalAttachments.tsx`
- `frontend/src/portal/PortalLogin.tsx`

## Verification Results
4/4 verification commands passed (run by Triad after the agent finished).

## Verification Commands
| Command | Exit Code | Result |
|---------|-----------|--------|
| `cd frontend && npm run typecheck` | 0 | PASS |
| `cd frontend && npx vitest run` | 0 | PASS |
| `cd frontend && npm run build` | 0 | PASS |
| `cd frontend && npx vitest run src/PortalPolish.test.tsx` | 0 | PASS |

## Key Decisions
- A ticket counts as closed for the upload input when `status === "closed"`, matching the backend rule.
- The "Unlink Microsoft" button is shown to anyone who can edit organizations (`org:write`), as the plan says.
- `ExportButton` renders a plain `<a download>` link.
- The tenant ID help text sits outside the `Field` label so the input's accessible name stays "Client Entra tenant ID".

## Issues Encountered
- `PortalMeOut` (`backend/app/schemas.py`, `svc.me`) has no `phone` or `title`, and `backend/` is off limits to me. My details starts those two fields blank, and saving without retyping them clears them (`PortalContactPatch` treats a blank value as null). The page prefills them if the API starts returning them (they are optional on `PortalMe`).

## Escalations
| # | Severity | Type | Decision | Status | Resolution |
|---|----------|------|----------|--------|------------|
| 1 | warning | api-contract | Add `phone` and `title` to `PortalMeOut` (and `svc.me`) so My details can prefill them and not wipe them on save. | pending | INVALID: type "api-contract" is not one of architecture, dependency, scope, schema, api, deletion, infrastructure, quality |

- #1 context: `backend/` is out of scope for this plan. Until it is changed, a contact who saves My details with those fields empty loses their stored phone and title.

## Handoff Context
- **Key outputs**: README.md; docs/verify/portal-polish.md; frontend/src/PortalPolish.test.tsx; frontend/src/api.ts; frontend/src/pages/OrganizationDetail.tsx; frontend/src/pages/TicketDetail.tsx; frontend/src/portal/ExportButton.tsx; frontend/src/portal/MyDetailsPage.tsx; frontend/src/portal/PortalApp.tsx; frontend/src/portal/PortalAttachments.tsx; frontend/src/portal/PortalLogin.tsx
- **Decisions made**: A ticket counts as closed for the upload input when `status === "closed"`, matching the backend rule.; The "Unlink Microsoft" button is shown to anyone who can edit organizations (`org:write`), as the plan says.; `ExportButton` renders a plain `<a download>` link.; The tenant ID help text sits outside the `Field` label so the input's accessible name stays "Client Entra tenant ID".
- **Open questions**: (none)
- **Conventions established**: Add `phone` and `title` to `PortalMeOut` and `svc.me` in a backend change. No frontend change is needed after that.; `docs/verify/portal-polish.md` and the Phase 14 items in `.planning/VERIFY.md` are ready for the Phase 15 manual walk-through.

## Requirements Covered
- REQ-13

## Token Usage
13 requests, 591192 input tokens (531286 cached), 17735 output tokens, $0.4334
