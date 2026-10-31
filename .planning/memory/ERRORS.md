# Pitfalls

Project-specific pitfalls recorded via `/triad:learn`.
Referenced by `/triad:plan` and `/triad:build` for context-aware execution.

## PIT-001: Any table with organization_id needs forced org_scope RLS
- **Date**: 2026-10-29
- **Type**: pitfall
- **Tags**: rls, migrations, planning, tests
- **Phase**: 11

tests/test_isolation.py (and test_backup_restore.py) require every table with an organization_id column, nullable or not, to have ENABLE + FORCE RLS and an org_scope policy; only audit_log is exempt. Phase 10 planned purchase_orders/inventory_items as staff-internal with a nullable organization_id and broke it; the review's subset checks missed it, and only the full suite caught it. Use the expenses precedent: the standard app_org_visible(organization_id) policy, under which staff ('all') see NULL rows and a client scope never does. Put test_isolation.py and test_backup_restore.py in the verification_commands of every schema plan.

---

## PIT-002: Ship gate is local only: check GitHub CI on the pushed commit
- **Date**: 2026-10-31
- **Type**: pitfall
- **Tags**: ci, ship, openapi, dependencies
- **Phase**: 12

The triad ship gate runs the checks in this sandbox and never reads GitHub Actions. Phases 10-12 shipped while CI on dev had been red for 10 runs: the committed OpenAPI spec was generated with FastAPI 0.143 locally, but CI installed 0.162 because backend deps were unpinned. Rules: (1) after every push, read the CI run for the pushed commit (mcp__github__actions_list on branch dev) and treat red CI as a blocker before reporting shipped or done; (2) backend installs use backend/constraints.txt (pip install -e ".[dev]" -c constraints.txt, Python 3.12, the CI version); run generators such as python -m app.openapi_export in that environment, never the sandbox's unpinned packages.

---
