# Phase 13: Knowledge base -- Context

## Phase Goal
Staff and clients find answers in internal and client-facing knowledge-base articles, with search and article suggestions on the ticket page.

## Requirements Covered
- REQ-12

## What Already Exists (from prior phases)
- Phase 12: every route under /api/v1, committed docs/api/openapi.json guarded by tests/test_api_v1_and_openapi.py (regenerate with the pinned venv, PIT-002)
- Permissions are plain strings in backend/app/permissions.py with a role MATRIX; test_zz_api_contract requires summary, tag, a permission dependency and a test hitting every route
- Portal auth is a contact cookie (portal_deps.portal_required) scoped to one org; portal frontend in frontend/src/portal/PortalApp.tsx
- Staff-internal tables without organization_id follow 0032_reporting.py (grants, no RLS); alembic head is 0033
- Search today is ILIKE only (routers/search.py); TicketDetail.tsx is one space-y-4 stack of Card components; text is rendered plain with whitespace-pre-wrap, no markdown library

## Key Design Decisions
- One table kb_articles with NO organization_id: articles are the MSP's own content, shared across clients, so outside RLS (like report_schedules); test_isolation does not require RLS for it
- Columns: id, title (<=200), body (plain text, <=50000), visibility internal|client, status draft|published|archived, tags text[] (<=10 tags, each <=40 chars, lower-cased, deduplicated), created_by_id/updated_by_id FK users nullable, created_at, updated_at, and search tsvector GENERATED ALWAYS AS (setweight(to_tsvector('english', title),'A') || setweight(to_tsvector('english', body),'B')) STORED with a GIN index
- No DELETE grant: articles are archived, never deleted; edits are audited (kb_article.create / kb_article.update with before/after snapshots)
- Search uses websearch_to_tsquery('english', q) ranked by ts_rank, falling back to title ILIKE when the tsquery is empty (stop-words only)
- Permissions (assumed, auto default): kb:read added to the _READ base so every staff role reads; kb:write for admin and tech only
- Ticket suggestions: GET /api/v1/kb/suggestions?ticket_id= (kb:read); the ticket is loaded through ctx.scope (404 if not visible); terms = up to 12 distinct words of 3+ letters/digits from subject + description, OR-joined into to_tsquery('english', ...), published articles of either visibility, top 5 by ts_rank; empty list when no terms
- Portal sees only status=published AND visibility=client; anything else is 404, never 403, so drafts and internal articles are not revealed
- Rendering stays plain text (whitespace-pre-wrap); no markdown library or dangerouslySetInnerHTML
- Light process (phase 13): no board/spec/security scan; 2 plans in 2 waves, backend first

## Plan Structure
- **Plan 13-01 (Wave 1)**: Knowledge base backend: schema, permissions, staff, suggestion and portal APIs -- Add the kb_articles table with full-text search, kb:read/kb:write permissions, the staff article API, ticket suggestions and the client-only portal KB API, with tests, seed data and the regenerated OpenAPI spec.
- **Plan 13-02 (Wave 2)**: Knowledge base frontend: staff pages, ticket suggestions card, portal pages, docs -- Give staff a knowledge-base list, search and editor, show suggested articles on each ticket, add a client-facing KB section to the portal, and document the manual checks.
