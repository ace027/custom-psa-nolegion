# Quoting: what to verify manually

Prep: as admin open **Quotes > Rate card**, set per-user $100, workstation $20, server $100 (hardware uplift stays 25%). Make sure Settings has your company name/address. Optionally configure a mailbox.

- [ ] A tech sees **Quotes** in the nav; `billing@example.com` can open it read-only (no schedule form); the rate card is read-only for the tech
- [ ] **Schedule a site survey** with "New prospect": it appears in Organizations as a purple *prospect*
- [ ] On a phone-width window: open the survey, enter 10 users, 8 workstations (5 *out of warranty*), 1 server in warranty, one legacy app. Layout is usable one-handed
- [ ] Type some answers, reload the page *before* saving: the yellow "Restored unsaved changes" notice appears; **Save** clears it
- [ ] Setting a warranty **date** in the past marks a device out of warranty regardless of the dropdown
- [ ] **Save and complete**: fields lock; **Create quote** appears
- [ ] The quote shows base $1,260.00, hardware +25% with "5 of 9 priced devices (56%)...", price **$1,575.00**; with only 4 of 9 out of warranty there is **no** uplift
- [ ] Download the PDF: client name, price, the build-up table; no internal notes
- [ ] As tech, change the price with a reason: "Submit for approval"; the tech has no Approve button; the quote shows in the list as *needs approval*
- [ ] As admin: Approve works; trying to approve a change you made yourself is refused
- [ ] **Mark as sent** (or email it): the quote can no longer be edited; email arrives with the PDF if a mailbox is configured
- [ ] **Client accepted** with a start date: prospect becomes active; Billing > Agreements shows a flat 12-month agreement at the quoted price
- [ ] Next monthly run includes that agreement (full month, no proration)
- [ ] Survey the same client again with all devices in warranty; **Create quote > Reprice** with the 1st of next month: after accepting, the old agreement ends the day before and the new, lower one starts; this month's invoice is unchanged
- [ ] Rate-card change does not alter an existing quote; **Revise** picks up the new rates
- [ ] Audit log shows survey.*, quote.* and quote_settings.update rows
