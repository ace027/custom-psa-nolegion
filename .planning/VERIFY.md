# Deferred owner checks (Phase 14: Verify)

The owner does no manual testing between phases. Each phase adds its manual
checks here instead of asking for them, and Phase 14 runs the whole list in one
pass. Mark each item pass or fail (with a note) when it is run.

## Phase 1: Block-hour / retainer agreements
- [ ] Walk through docs/verify/billing-block-hours.md

## Phase 2: Scheduling: availability & appointments
- (no manual checks; covered by automated tests)

## Phase 3: Dispatch board
- [ ] Walk through docs/verify/dispatch-board.md
- [ ] Walk through docs/verify/dispatch-spike.md
- [ ] e2e smoke.spec.ts "ticket lifecycle" fails before phase 4; confirm it is fixed or fix it

## Phase 4: Outlook push + free/busy
- [ ] Create the "PSA Techs" group and Exchange RBAC for Applications scope (docs/CALENDAR_SETUP.md)
- [ ] Run `cd backend && python dev/graph_calendar_spike.py --mailbox <tech>` (read-only) on the real tenant
- [ ] Run it again with `--write`, then with `--write --outside <someone outside the group>`; the outside call must be refused
- [ ] Turn on Outlook sync in Settings; book, move, reassign and cancel an appointment and check each tech's Outlook calendar
- [ ] Put a meeting in a tech's Outlook; within 5 minutes the board shows hatched busy time with the cache-age caption
- [ ] Force a failure (e.g. a tech outside the group); the board shows the failed badge and Retry works after fixing it

## Phase 5: Client confirmations + on-call
- [ ] Walk through docs/verify/client-notices-oncall.md

## Phase 6: RMM alerts to tickets
- [ ] Walk through docs/verify/rmm-alerts.md
- [ ] Check the NinjaOne alert field names (uid, deviceId, severity, sourceConfigUid) against a live tenant first
- [ ] Enable alerts with defaults on the Integrations card
- [ ] A MODERATE+ alert on a mapped device makes one RMM ticket with device link and severity priority
- [ ] A repeating alert raises occurrences and makes no second ticket
- [ ] A MINOR alert makes no ticket
- [ ] An unsynced device makes no ticket until asset sync
- [ ] Clearing an untouched alert resolves the ticket with a note
- [ ] Clearing after a tech note adds a note only and the ticket stays open
- [ ] Rules note_only and always_resolve behave as labelled
- [ ] Re-firing after resolve makes a new ticket linked as related
- [ ] Broken credentials show an error on the card and change no tickets
- [ ] Check now queues a poll and is disabled while alerts are off
- [ ] Tech and read-only users cannot see the card

## Phase 7: Automation & API
- [ ] Walk through docs/verify/automation-api.md (API keys, webhooks, automation rules)
- [ ] Unverified: a real Microsoft Teams Workflows webhook URL renders the adaptive card
- [ ] Unverified: a real n8n instance accepts the payload and the HMAC-SHA256 signature verifies
- [ ] Unverified: a LAN n8n works with WEBHOOK_ALLOW_PRIVATE_HOSTS=true (https only)
- [ ] A rule's assign, escalate, notify, webhook and create-ticket actions each work on a real ticket
- [ ] Rules never trigger other rules; a rule firing more than 200 times in an hour switches itself off
