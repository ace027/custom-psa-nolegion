# Phase 15: Verify (owner manual testing) -- Context

## Phase Goal
Give the owner one runbook to run every deferred manual check from phases 1-14 in a single pass, record pass/fail per item, and turn failures into fix tasks before release.

## Requirements Covered
- Every item in .planning/VERIFY.md has a place for the owner to mark pass/fail/deferred
- Each failure has a fix committed and re-checked, or an owner-accepted deferral
- Real-tenant Outlook spike (backend/dev/graph_calendar_spike.py incl. --write and --outside) is in the runbook

## What Already Exists (from prior phases)
- .planning/VERIFY.md lists deferred owner checks per phase 1-14
- docs/verify/*.md holds 32 per-feature manual checklists
- backend/dev/graph_calendar_spike.py is the Outlook real-tenant spike
- docs/PORTAL_SSO.md documents the portal multi-tenant app registration

## Key Design Decisions
- Agents cannot run real-tenant or real-vendor checks; this phase's buildable work is the consolidated owner runbook plus a mechanical coverage check. The owner then runs it; failures come back as /triad:quick fixes.
- The runbook is docs/verify/RUNBOOK.md; .planning/VERIFY.md stays the source list and gains a Result column, no items removed.
- No application code changes in this phase.

## Plan Structure
- **Plan 15-01 (Wave 1)**: Owner verification runbook -- Write docs/verify/RUNBOOK.md, one ordered pass through every deferred owner check and every docs/verify checklist, with result tracking, and add a Result column to .planning/VERIFY.md.
