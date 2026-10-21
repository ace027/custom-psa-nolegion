# Verify: API keys, webhooks and automation rules (Phase 7)

Run this once in Phase 14. Mark each item pass or fail with a note.

## Prerequisites
- You are an admin. The worker is running (it sends webhooks and mail).
- A Microsoft Teams channel with a Workflows webhook URL, and an n8n instance that can receive a webhook.
- For a LAN n8n: `WEBHOOK_ALLOW_PRIVATE_HOSTS=true` is set (URLs must still be https).

## API keys
- [ ] 1. Create an API key (Settings > API keys) with ticket read. Expect the token shown once.
- [ ] 2. `curl -H "Authorization: Bearer <token>" https://<host>/api/tickets` returns tickets; without the header it is refused.
- [ ] 3. Revoke the key. The same call is now refused. The audit log shows the create and the revoke.

## Webhooks
- [ ] 4. Webhooks page: add a Teams webhook for "A ticket is created". Click Send test; a test card shows in the channel.
- [ ] 5. Create a ticket. Within a minute a card shows with client, priority, status, assignee and an "Open ticket" button.
- [ ] 6. Add a generic webhook pointing at n8n. Copy the secret when shown (it appears once).
- [ ] 7. In n8n verify the signature: HMAC-SHA256 of `<X-PSA-Timestamp>.<raw body>` with the secret equals `X-PSA-Signature` (v1=...).
- [ ] 8. Edit the URL to a broken one and create a ticket. The delivery log shows retries, then "failed" after 6 attempts; the endpoint shows a failures badge. Fix the URL, press Retry; it delivers.
- [ ] 9. Try a http:// URL and a private address (with the LAN opt-in off). Both are refused.

## Automation rules
- [ ] 10. Automation page: build "Security to a tech" (When a ticket is created, Queue is Security, assign to a tech). Create a ticket in the Security queue; it is assigned to that tech and the rule's run history shows the trace.
- [ ] 11. Build "Critical alerts" (When a monitoring alert opens a ticket, Alert severity is Critical, raise priority one step). Trigger a critical RMM alert; the ticket priority rises and gets an internal note.
- [ ] 12. Test against ticket # with a ticket that does not match: the page shows which condition failed and the ticket's actual value. Nothing changes on the ticket and no run is added.
- [ ] 13. With a webhook subscribed to "A ticket is assigned", confirm the assign by the rule still sends the webhook but does not trigger a second rule on "A ticket is assigned".
- [ ] 14. Switch a rule off with the toggle; it stops running. Archive one; it disappears from the list.
- [ ] 15. Settings > Audit log shows automation.rule_created, rule_updated, rule_fired and rule_archived entries.
