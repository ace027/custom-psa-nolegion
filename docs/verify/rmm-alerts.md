# Verify: NinjaOne alerts to tickets (Phase 6)

Run this once in Phase 15. Mark each item pass or fail with a note.

## Prerequisites
- A NinjaOne integration is connected and "Test connection" passes.
- The NinjaOne clients are mapped to organizations and an asset sync has run, so the test device exists as an asset.
- The worker is running.
- Note: the NinjaOne alert field names are unverified against a live tenant. Before anything else, check that the
  uid, deviceId, severity and sourceConfigUid fields the poller reads match a real alert from your tenant. If they
  do not, stop and report it; nothing below will behave.

## Checks
- [ ] 1. Integrations page, "Alerts to tickets" card (admin only): tick "Create tickets from alerts" and keep the
  defaults (Moderate, resolve if nobody has worked the ticket, every 5 minutes). Save. Expect it to save and, after
  a moment, "Last checked ..." to appear.
- [ ] 2. Trigger a MODERATE or higher alert on a mapped, synced device. Within the poll interval expect exactly one
  ticket with source RMM, a "From RMM alert" badge, a "Device: <name>" link to the organization, and a priority that
  matches the severity. The alert shows in the Open list with a link to the ticket.
- [ ] 3. Let the alert repeat. Expect "Times" to rise and no second ticket.
- [ ] 4. Trigger a MINOR alert. Expect no ticket.
- [ ] 5. Trigger an alert on a device that has not been synced yet. Expect no ticket until the next asset sync, then
  one ticket.
- [ ] 6. Clear an alert nobody has worked. A clear needs two polls in a row without the alert (use Check now
  twice); after the first the ticket is unchanged. Expect the ticket resolved with a note, and the alert under Cleared with
  "Ticket resolved".
- [ ] 7. Trigger another alert, add a note to its ticket, then clear the alert. Expect a note only; the ticket stays open.
- [ ] 8. Switch the rule to "Add a note only" and repeat 6: expect a note and the ticket stays open. Switch to
  "Always resolve" and repeat 7: expect the ticket resolved even after a tech note.
- [ ] 9. Re-fire an alert for the same condition after it was resolved. Expect a new ticket linked to the old one as "Related to".
- [ ] 10. Break the credentials (Replace credentials with wrong values). Expect the error on the card within a poll
  interval and no changes to existing tickets. Restore them and the error clears on the next check.
- [ ] 11. Click "Check now". Expect "Check queued", then "Last checked" updates within about a minute. With alerts
  turned off the button is disabled.
- [ ] 12. Sign in as a tech and as a read-only user. Expect no Integrations page and no alerts card.
- [ ] 13. Make NinjaOne return an empty alert list while alerts are open (for example by clearing all of them at once).
  Expect nothing to clear for two polls and the card to read "NinjaOne returned no active alerts while N are open;
  clears wait for 3 empty polls in a row". On the third empty poll in a row the alerts clear (a real all-clear).
- [ ] 14. Create more than 25 new alerts at once. Expect 25 tickets on the first poll, the card to read "N new alert(s)
  deferred to the next poll (limit 25 per poll)", and the rest on the next poll.
- [ ] 15. Sign in to the portal as a contact on a monitoring ticket. Expect the description to read "Monitoring alert
  on <device>" with no device id or condition key; the subject is unchanged.
