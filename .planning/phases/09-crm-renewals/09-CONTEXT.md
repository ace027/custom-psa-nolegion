# Phase 9: CRM & renewals -- Context

## Phase Goal
Sales work is tracked from lead to agreement, with renewal reminders.

## Requirements Covered
- REQ-09: leads and opportunities with pipeline stages and a forecast view; accepted quote converts to an agreement; renewal reminders generated ahead of agreement end dates

## What Already Exists (from prior phases)
- Organizations have status 'active'|'inactive'|'prospect' (ck_organizations_status); services.create_organization(ctx, data); Contact requires organization_id
- Quotes (models.py Quote, app/quoting.py) belong to an organization; final_price_cents is a monthly flat fee with term_months; accept_quote(ctx, quote_id, start_date, note) already creates the agreement (resulting_agreement_id), sets end_date = contract_end(start, term) and flips a prospect org to active; decline_quote(ctx, quote_id, note); routes need quote:manage
- Agreement(organization_id, name, type, unit_price_cents, quantity, taxable, start_date, end_date nullable, ...); billing.monthly_amount_cents(a) -> int
- Worker billing_jobs() runs notices.run_scheduled (idempotent per day); outbound mail via EmailMessage outbox when a mailbox is configured (see notifications.notify)
- money.round_cents for Decimal rounding; client-scoped tables use organization_id + ENABLE/FORCE RLS org_scope app_org_visible; staff-internal tables have no RLS
- Latest migration 0029; conftest TABLES and RESEED in tests/conftest.py

## Key Design Decisions
- No money rules change: CRM amounts are estimates for forecasting only and never bill; agreements are still created only by accept_quote.
- Leads are staff-internal (no organization_id, no RLS, like users): name, company, email, phone, source, status 'new'|'contacted'|'qualified'|'disqualified'|'converted', owner_id, notes, converted_organization_id, converted_at. Converting a qualified lead creates an Organization with status 'prospect', a primary Contact (name, email, phone) and an open Opportunity at the first open stage; a converted lead is read-only.
- Pipeline stages are a staff config table opportunity_stages (name, position, probability_bp 0..10000, kind 'open'|'won'|'lost', active) seeded by the migration with: Qualify 10%, Site survey 25%, Proposal 50%, Negotiation 75% (open), Won 100% (won), Lost 0% (lost). Exactly one active won and one active lost stage must exist; managed with config:manage.
- Opportunities are client-scoped (organization_id NOT NULL, ENABLE + FORCE RLS, composite FKs): name, kind 'new'|'renewal'|'upsell', stage_id, owner_id, monthly_cents >= 0, term_months 1..120 default 12, expected_close_date, quote_id (same org), agreement_id (renewal target or won result), lost_reason, closed_at, notes. Moving to a won/lost stage sets closed_at; lost requires lost_reason; reopening clears closed_at.
- Quote link: an opportunity may link one quote of the same organization. accept_quote moves every open opportunity linked to that quote to the won stage and sets agreement_id = the resulting agreement (renewal opportunities keep their agreement_id and also record won). decline_quote does not close the opportunity.
- Forecast: for open opportunities by expected close month (next 12 months plus 'overdue' and 'no date' buckets): count, monthly_cents total, weighted_monthly_cents = sum of round_cents(monthly_cents * probability_bp / 10000) per opportunity (ROUND_HALF_UP via money.round_cents), contract_value_cents = sum monthly_cents * term_months; plus won this month/quarter totals. Read-only, crm:read.
- Renewals: settings gain renewal_reminder_days (integer array, default {90,30}) and renewal_email (nullable). A worker job (in billing_jobs after run_scheduled) finds agreements with end_date not null, end_date >= today, and today >= end_date - N days for each N; it inserts renewal_reminders(organization_id, agreement_id, lead_days, due_on=end_date, status 'open'|'done'|'dismissed') with UNIQUE(agreement_id, lead_days), so each is created once. At the first reminder for an agreement it creates a renewal opportunity (kind 'renewal', first open stage, monthly = monthly_amount_cents(agreement), term 12, expected_close_date = end_date, agreement_id) unless an open renewal opportunity for that agreement exists. If renewal_email is set and a mailbox is configured, it queues one plain email per new reminder (facts only: client, agreement, end date, link), dedupe by the reminder row. Reminders for an agreement whose end_date is moved later stay; new ones are created for the new dates. A reminder is marked done when its renewal opportunity is won or lost.
- Permissions: crm:read for every staff role (part of _READ); crm:write for admin and tech; stage config uses config:manage.
- PRF-001: plan 09-03 writes docs/verify/crm.md and appends the Phase 9 section to .planning/VERIFY.md.

## Plan Structure
- **Plan 09-01 (Wave 1)**: CRM schema, stages and permissions -- Add migration 0030 with leads, opportunity_stages (seeded), opportunities, renewal_reminders and the renewal settings columns, the models, the crm permissions and schema tests.
- **Plan 09-02 (Wave 2)**: CRM service, quote link, forecast and renewal job -- Leads (with convert), opportunities and stage moves, stage config, the forecast, linking quotes with the accept hook, and the renewal reminder worker job, all with routes and tests.
- **Plan 09-03 (Wave 3)**: Sales pipeline, forecast and renewals UI, docs and verify checklist -- A Sales area with leads, a pipeline board by stage, opportunity detail, the forecast view and the renewals list; links from org and quote pages, a dashboard renewals card, settings fields, stage config, docs and the Phase 9 checklist.
