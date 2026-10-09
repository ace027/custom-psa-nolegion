# New-client quoting: how it works

Built from the approved plan in [QUOTING_PLAN.md](QUOTING_PLAN.md). Flow:
**prospect -> onsite survey (phone/tablet) -> priced quote -> approval -> proposal PDF -> sent -> accepted -> flat-fee agreement.**

## The pricing rules (tested; change them deliberately)
1. **Base** = users x per-user rate + (priced devices of each class x that class's rate). Rates are in **Quotes > Rate card** (admin). A rate of $0 means that line is not used, so you can price per user, per device, or both.
2. **Uplifts** are percentages that apply when a rule is true, and they **add** (25% + 15% = +40%), never compound:
   - **Hardware** (default **25%**): applies when **more than half** of the priced devices are **out of warranty**. Exactly half does not apply.
   - **Server** (default 0%): any priced server is out of warranty.
   - **Legacy application** (default 0%): the survey lists a legacy / unsupported line-of-business app.
3. **Price** = `round_half_up(base x (10000 + total uplift in basis points) / 10000)`, rounded **once** (integer cents).
4. **"Out of warranty"** = a warranty end date in the past, or the tech marked it out. **Unknown counts as out** so the surcharge is never skipped by accident; the quote says how many were unknown. A device can be marked *not covered* (e.g. a personal printer) and is then excluded from price and from the half test.
5. **No onboarding fee.** The monthly flat fee includes it; the term (default 12 months) and validity (default 30 days) are in the rate card.
6. A quote **freezes its numbers** (rates, counts, reasons) when created. Later rate-card edits never change it; **Revise** re-prices at today's rates as a new version.

## Roles
| Who | Can |
|---|---|
| tech, admin (`quote:write`) | schedule/fill surveys, create quotes, adjust the price (with a reason), submit, send, revise, cancel |
| admin (`quote:manage`) | edit the rate card, **approve** adjusted prices, record the client's acceptance/decline |
| everyone signed in (`quote:read`) | view surveys, quotes, the rate card, download the PDF |

## Approval
- A quote priced exactly by the rate card needs **no approval**: Submit approves it.
- Any change to the price needs a **reason** and goes to **needs approval**; an **admin** approves (or sends it back with a note). You **cannot approve your own change**.
- An admin's own adjustment is approved when they submit it (they are the approver). A tech's adjustment always needs an admin.
- Editing an approved quote sends it back to draft: what is sent is always what was approved.
- The internal reason is **never** printed on the client's PDF; the PDF shows the base, the uplifts and a "Pricing adjustment" amount.

## Sending, accepting, repricing
- **Send** marks the quote sent and **locks it** (database trigger). Tick "email the PDF" to queue it to the client's primary contact (or addresses you enter). It goes through the normal outbox/worker, requires a configured mailbox, and the approval above is the human review. Otherwise download the PDF and send it yourself.
- **Accept** (admin) records the client's yes: the prospect becomes **active** and a **flat-fee agreement** is created (name "Managed services (quote Q-n)", the quoted price, start date you choose, ends after the term). It then bills through the normal monthly run, with the usual **no-proration** rule (a mid-month start bills the full month; adjust in the run review).
- **Decline** keeps the prospect as a prospect.
- A sent quote is valid until its date; after that it shows *expired*, and accepting is refused (Revise to issue a current one).
- **When the environment improves (reprice):** survey again, then "Reprice an existing flat-fee agreement" with an effective date (the **1st of a future month**). On acceptance the old agreement ends the day before and a new one starts at the new price, keeping the old agreement's end date, so price history is two agreements, never an edited number. Refused if the old agreement is already invoiced from the effective date on.

## Surveys
- Phone-friendly form: users, sites, notes, devices (class, name, make/model, serial, warranty date or status, covered yes/no), legacy apps. **Save** stores the whole survey; **Save and complete** freezes it (database trigger): it is the evidence behind the quote.
- Unsaved answers are kept **in the browser** and restored after a dropped connection or closed tab; this is not an offline app, you need signal to save.
- Prospects are organizations with status **prospect** (same isolation and audit as clients; they hold no billing until accepted).

## Things to check
- **Contract wording.** The proposal says the price reflects support effort and that additions come off the price after a re-assessment. Have your contract say the same.
- Warranty "unknown = out" is deliberately conservative; set the dates on site to avoid surprising a client.
- The hardware test counts **all priced devices** (workstations, servers, network, other), as you decided.

## Not built (see BACKLOG.md)
Photos on surveys, true offline mode, e-signature / portal acceptance, scheduling the visit as a ticket/calendar entry, extra custom uplift factors, importing the survey from NinjaOne/Hudu once vCISO Phase 1 exists.
