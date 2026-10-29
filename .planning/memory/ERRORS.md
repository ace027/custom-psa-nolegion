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
