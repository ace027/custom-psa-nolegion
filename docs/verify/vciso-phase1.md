# Manual check: vendor integrations and warranty (vCISO Phase 1)

Needs: an admin login, a tech login, a portal contact with an email, and either real NinjaOne/Hudu read-only accounts or the automated tests (which use fake vendors).

## Setup
- [ ] `CREDENTIALS_KEY` is set in `.env` (see docs/INTEGRATIONS.md) and `api` + `worker` were restarted.
- [ ] Settings page nav shows **Integrations** for the admin and **not** for the tech.

## Connect and map (admin)
- [ ] Integrations > Connect a vendor > NinjaOne with a read-only client app. The card shows "credentials set" and a date, and never the secret.
- [ ] **Test connection** says it works. Enter a wrong secret on a scratch connection: it says the sign-in failed and the card turns red.
- [ ] Clients and history > **Fetch client list**. Vendor clients appear as "to map"; a same-name match shows **Use suggested match**; nothing is mapped until you click.
- [ ] Map one client, ignore another. Unmapped clients stay listed as a to-do.

## Sync
- [ ] **Sync now**; within about a minute the card shows a recent successful sync and the history row shows added counts.
- [ ] Open the mapped client's page: **Devices and warranty** lists devices with status badges. Compare 3 devices to NinjaOne.
- [ ] Press Sync now again: history shows 0 added / 0 changed.
- [ ] Connect Hudu with the layout JSON; map the same client; sync. A switch that is in both systems appears once. A device with differing dates shows **sources disagree**.
- [ ] Devices with no warranty date show **Unknown**, not "expired".

## Corrections (tech)
- [ ] As the tech: **Correct date** on a device, with a reason. The date and status change and it shows **corrected**.
- [ ] Sync now: the corrected date is still there. **Undo** returns the vendor's date.
- [ ] As a read-only user, the Correct date button is absent.

## Failure handling
- [ ] Turn the vendor's secret wrong (Replace credentials with a bad value) and Sync now. The run shows failed with a clear error, the card is red, and the device list is unchanged.
- [ ] Put the right credentials back; the next sync is green.

## Warranty report (admin or billing)
- [ ] **Warranty** page lists expired and soonest-expiring first; filters for client, window and status work; the CSV opens in a spreadsheet and matches the screen.
- [ ] The tech does not see the Warranty page.
- [ ] Audit log shows the CSV download, credential changes, mapping changes and corrections, with no secrets in any row.

## Client portal
- [ ] Contact with portal access but no devices flag: no Devices tab.
- [ ] Publish the client and flag the contact: the Devices tab appears with totals and a list, no serial numbers.
- [ ] Withdraw the publish switch: the tab disappears and the page returns "not available".
- [ ] A contact of another client sees none of this client's devices.

## Backup and key
- [ ] A database dump contains no readable vendor secrets (`SELECT credentials FROM integrations` shows ciphertext).
- [ ] Practice rotation on a test copy: `CREDENTIALS_KEY=new,old`, `python -m app.rekey`, remove `old`, Test connection still works.
