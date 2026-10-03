# New-client quoting: plan

Status: **PLAN ONLY. Nothing here is built.** No code starts until you say "go".
Items marked **(assumption)** were not confirmed and should be checked before building.

## 1. Goal
Turn an onsite survey of a prospect's environment into a defensible, consistent quote for a
**flat-fee, 12-month managed-services contract**. The price is a base (per user and/or per
device) plus a **difficulty uplift** for environments that are harder to support. Onboarding is
built into the price; there is no separate onboarding fee.

## 2. Decisions made so far
| Topic | Decision |
|---|---|
| Contract shape | Flat monthly fee, 12-month term, set from the client's initial environment |
| Base price | Per user and/or per device, from an editable rate card |
| Onboarding | Rolled into the contract; never a line item |
| "Old hardware" | **Out of warranty** (not an age cutoff) |
| Hardware uplift | **+25%** when **more than half** of the priced devices are out of warranty |
| Combining uplifts | **Add** (25% + 15% = +40%), never compound |
| Environment improves | The extras **go away**, to reward paying down technical debt |
| Survey | Onsite, captured by a tech on a phone or tablet |
| Tech price changes | Need **approval** |

## 3. How the price is built
1. **Base** = (users × per-user rate) + (devices × per-device rate, by device class).
   The rate card is a setting; which parts apply to a quote is the tech's choice
   ("per user", "per device" or both).
2. **Uplift factors**, each an editable percentage that applies when its rule is true:
   - *Hardware*: more than 50% of priced devices are out of warranty: **25%** (your number).
   - *Others* (old server, legacy line-of-business app, and so on): start at **0%** and are tuned by you.
     Each factor is a yes/no rule over the survey, so adding one later is a settings change, not a code change.
3. **Total uplift** = sum of the factors that apply.
4. **Monthly price** = base × (1 + total uplift), rounded once, half-up, to whole cents (integer cents, same as billing).
5. The quote shows **why**: "14 of 20 devices out of warranty (70%): +25%".

Worked example: 20 users at $X and 22 devices at $Y; 14 devices are out of warranty, so the hardware
factor applies. Base × 1.25 = monthly price. If a legacy-app factor of 15% were set and applied,
the multiplier would be 1.40.

## 4. Survey (onsite, phone / tablet)
- Responsive web form in the PSA, designed for one-handed use: big targets, sections, quick add.
- Per prospect: users, sites, **devices** (class: workstation / server / network / other;
  make/model; serial; **warranty end date or in/out of warranty**; notes), Microsoft 365 / cloud
  setup, line-of-business apps (name, vendor-supported yes/no, legacy yes/no), backups,
  security basics, anything else you want added (open question below).
- Photos and notes attach to the survey (existing attachment storage).
- **Poor signal (assumption):** drafts autosave in the browser and submit when online. A true
  offline app is out of scope for v1 and goes to the backlog.
- **Unknown warranty** (assumption): counts as out of warranty for the >50% test, but is shown
  separately so the tech can look it up. Needs your confirmation.
- Later, once a prospect becomes a client, NinjaOne/Hudu data (vCISO Phase 1) can verify the survey and drive the re-survey below.

## 5. Approval
- A quote that is exactly what the rules compute needs no approval **(assumption)**.
- Any tech change to the price (a base override, adding/removing an uplift, a discount) requires a reason and
  **sits in "needs approval" until an approver accepts it**. The approver cannot be the person who made the change.
- New permissions: `quote:read`, `quote:write` (techs), `quote:approve` (admin only). All
  approvals, rejections and overrides are audited.
- Approval is recorded on the quote and visible in the PDF history; the client sees only the final price and reasons.

## 6. Quote life cycle
`draft` → `needs_approval` (only if adjusted) → `approved` → `sent` → `accepted` / `declined` / `expired`.
- A sent quote is **immutable** (DB trigger, same as invoices); changes create a new version.
- The quote stores a **snapshot** of the rates, factors and survey counts used, so later rate-card edits never change it.
- Default validity 30 days, editable **(assumption)**.
- PDF proposal, branded, emailed through the existing review-before-send queue (nothing goes out unapproved).
- **Acceptance (assumption):** v1 records acceptance by staff (client replies to the email or returns the signed PDF; the file is attached). Portal "accept" and e-signature go to the backlog.

## 7. Prospects and conversion
- **Decision to confirm:** model a prospect as an organization with status `prospect`
  (assumption), so surveys and quotes use the same multi-tenant isolation (row-level security) as everything else,
  and conversion is a status change with no data copying. Prospects are excluded from client lists, billing and reports by default.
- Scheduling the visit: a "survey visit" with date and assigned tech, shown on the prospect and as a ticket so it shows in the normal queue **(assumption; needs your preference)**.
- **On acceptance:** the prospect becomes an active client and a flat-fee agreement is created
  (12-month term, start date chosen, monthly amount = the quote price). Existing agreement
  structure will be checked first; if it lacks term or flat-fee fields, a migration adds them.

## 8. When the environment improves (the part to get right)
Your rule: when the extras go away, the price drops. To keep this auditable:
- A **re-survey** (onsite, or later verified from NinjaOne/Hudu) recomputes the quote with the same rate card.
- If a factor no longer applies, the proposed new monthly price goes through **approval**, then takes effect on the **next billing period** (never retroactive; finalized invoices stay untouched).
- The agreement keeps a **price history with effective dates**, not an edited number, so "why did the price change" is always answerable.
- Re-survey can be requested by the client or scheduled by a tech; at the 12-month renewal the same process runs automatically.
- **Worth flagging:** this is a price decrease mid-contract. The contract language needs to say so; that wording is outside the PSA.

## 9. Data model (sketch)
All client-owned tables carry `organization_id` with forced RLS, covered by the existing guard test.
- `quote_rate_card` / settings: per-user rate, per-device rates by class, uplift factors (name, rule, basis points, enabled).
- `site_surveys`: organization, scheduled_for, tech, status, completed_at.
- `survey_devices`, `survey_apps` (and users/sites counts on the survey).
- `quotes` (+ `quote_versions`): status, snapshot (JSON), base cents, uplift basis points, price cents, adjustments with reason, approver, sent/accepted timestamps.
- Agreement price history (if not already present).
Money is integer cents; percentages are integer basis points.

## 10. Testing and acceptance
- Unit tests: base math, >50% boundary (exactly half does not trigger), unknown warranty handling, additive factors, rounding, snapshot stability.
- Approval: self-approval blocked, adjusted quote can't be sent unapproved, audit rows written.
- Immutability of sent quotes, RLS isolation for prospects, permission matrix and route contract coverage.
- Frontend tests for the survey form and quote view; mobile-width layout check.
- **Acceptance:** survey a prospect on a phone, get a price with a clear explanation, adjust it, have a second person approve it, send the PDF, record acceptance, and see a correct 12-month agreement; then re-survey with fewer old devices and see the price drop from the next period.

## 11. Not in v1
Offline mobile app, e-signature, portal acceptance, sales pipeline / forecasting, auto-import from NinjaOne/Hudu for prospects, payment integrations (never).

## 12. Open questions
1. Confirm the assumptions above (unknown warranty = out; unadjusted quotes skip approval; 30-day validity; staff-recorded acceptance; prospect as an organization).
2. What else should the survey capture (email platform, printers, phone system, remote workers, compliance needs)?
3. Is "over half" measured across all priced devices, or workstations only? (Recommend all priced devices.)
4. Who approves? Admin only, or a second tech?
5. Device-class rates: one device rate, or separate workstation / server / network rates?
6. Do you want the 12-month renewal re-survey to be automatic (a prompt) or manual?
