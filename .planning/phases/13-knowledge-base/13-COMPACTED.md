---
phase: 13-knowledge-base
compacted: 2026-10-31
original_summaries: [13-01-SUMMARY.md, 13-02-SUMMARY.md]
requirements_satisfied: [REQ-12]
---

# Phase 13: Knowledge base — Compacted Summary

## Deliverables
- 13-01 Knowledge base backend: schema, permissions, staff, suggestion and portal APIs (Complete): backend/tests/test_seed_and_migrations.py
- 13-02 Knowledge base frontend: staff pages, ticket suggestions card, portal pages, docs (Complete): README.md, docs/verify/kb.md, frontend/src/App.tsx, frontend/src/KnowledgeBase.test.tsx, frontend/src/api.ts, frontend/src/pages/KbSuggestionsCard.tsx, frontend/src/pages/TicketDetail.tsx, frontend/src/pages/kb/ArticlePage.tsx, frontend/src/pages/kb/KnowledgeBase.tsx, frontend/src/portal/KbPages.tsx, frontend/src/portal/PortalApp.tsx

## Decisions
- 13-01: I kept the earlier on-disk implementation instead of rewriting it. I spot-read `kb.py`, and it matches the context decisions.
- 13-01: `test_seed_and_migrations.py` was in the plan's files_modified list, so I edited it.
- 13-02: The search box sends q only when the trimmed text is at least 2 characters, because the API rejects shorter queries. A one-character entry shows a hint instead.
- 13-02: The portal list and the staff list use the same 300 ms debounce.
- 13-02: Tags are sent as typed (split on commas and trimmed); the backend lowercases and deduplicates them.

## Conventions and Open Questions
- 13-01 convention: The routes the frontend plan builds on are `/api/v1/kb/articles`, `/api/v1/kb/articles/{id}`, `/api/v1/kb/suggestions?ticket_id=`, `/api/v1/portal/kb` and `/api
- 13-01 convention: Any later migration must bump the head assertion in `test_seed_and_migrations.py`, now "0034".
- 13-01 convention: Portal responses omit status, visibility and author names. Internal, draft and archived articles return 404 from the portal.
- 13-02 convention: Staff routes are `/kb`, `/kb/new` and `/kb/:id`. The portal routes are `/portal/kb` and `/portal/kb/:id`.
- 13-02 convention: `VisibilityBadge` and `StatusBadge` are exported from `pages/kb/KnowledgeBase.tsx` for reuse.
- 13-02 convention: I did not write SUMMARY or STATE files and did not commit, as instructed.

## Files Modified
| File | Change |
|------|--------|
| `backend/tests/test_seed_and_migrations.py` | 13-01: Knowledge base backend: schema, permissions, staff, suggestion and portal APIs |
| `README.md` | 13-02: Knowledge base frontend: staff pages, ticket suggestions card, portal pages, docs |
| `docs/verify/kb.md` | 13-02: Knowledge base frontend: staff pages, ticket suggestions card, portal pages, docs |
| `frontend/src/App.tsx` | 13-02: Knowledge base frontend: staff pages, ticket suggestions card, portal pages, docs |
| `frontend/src/KnowledgeBase.test.tsx` | 13-02: Knowledge base frontend: staff pages, ticket suggestions card, portal pages, docs |
| `frontend/src/api.ts` | 13-02: Knowledge base frontend: staff pages, ticket suggestions card, portal pages, docs |
| `frontend/src/pages/KbSuggestionsCard.tsx` | 13-02: Knowledge base frontend: staff pages, ticket suggestions card, portal pages, docs |
| `frontend/src/pages/TicketDetail.tsx` | 13-02: Knowledge base frontend: staff pages, ticket suggestions card, portal pages, docs |
| `frontend/src/pages/kb/ArticlePage.tsx` | 13-02: Knowledge base frontend: staff pages, ticket suggestions card, portal pages, docs |
| `frontend/src/pages/kb/KnowledgeBase.tsx` | 13-02: Knowledge base frontend: staff pages, ticket suggestions card, portal pages, docs |
| `frontend/src/portal/KbPages.tsx` | 13-02: Knowledge base frontend: staff pages, ticket suggestions card, portal pages, docs |
| `frontend/src/portal/PortalApp.tsx` | 13-02: Knowledge base frontend: staff pages, ticket suggestions card, portal pages, docs |

## Verification
- 13-01 (REQ-12): 6/6 verification commands passed
- 13-02 (REQ-12): 4/4 verification commands passed

## Agents
- 13-01: engineering-backend-architect
- 13-02: engineering-frontend-developer

## Also Covered
- backend/alembic/versions/0034_knowledge_base.py
- backend/app/models.py
- backend/app/permissions.py
- backend/app/kb.py
- backend/app/kb_schemas.py
- backend/app/routers/kb.py
- backend/app/routers/portal.py
- backend/app/main.py
- backend/app/seed.py
- backend/tests/test_kb.py
- backend/tests/test_kb_portal.py
- backend/tests/test_permissions.py
- backend/tests/test_backup_restore.py
- docs/api/openapi.json
- .planning/VERIFY.md
