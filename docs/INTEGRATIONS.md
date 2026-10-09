# Vendor integrations and asset warranty (vCISO Phase 1)

Status: **built.** Plan and later phases: [VCISO_PLAN.md](VCISO_PLAN.md). Step-by-step check: [verify/vciso-phase1.md](verify/vciso-phase1.md).

The PSA pulls device inventory and warranty dates from **NinjaOne** (computers, servers) and **Hudu**
(network gear and anything else you document there), merges them into one asset list per client,
and reports on warranties. It is **read-only toward the vendors**: it never changes anything in them.

## Read this first: NinjaOne field names are not verified
NinjaOne's API reference could not be read during the build, so the adapter in
`backend/app/integrations/ninjaone.py` uses the documented sign-in and the `organizations` /
`devices-detailed` endpoints, but the **warranty and serial field names are best guesses**. Everything
vendor-specific lives in one function (`_to_asset`). On the first real connection:
1. Connect and map one small client, press **Sync now**, and look at the devices.
2. If warranty dates are blank, send one `GET /v2/devices-detailed?pageSize=1` response (redact
   serials if you like) and the field mapping gets fixed in that one function, with a test.

Hudu is documented from its public REST API (`/api/v1/companies`, `/asset_layouts`, `/assets`, `x-api-key`).

## What you get
- **Settings > Integrations** (admin): connect a vendor, test it, sync now, see status, history and errors.
- **Client mapping:** vendor clients are listed, never guessed. A name match is *suggested*; you click to accept. Unmapped clients are a to-do; "ignore" skips one.
- **Organization page > Devices and warranty:** the merged device list with warranty status, a "Correct date" action, and (admin) a switch to publish to the portal.
- **Warranty** (admin, billing): all clients, soonest expiry first, filter by client, window and status, CSV download (audited).
- **Client portal > Devices** (optional): see below.

## Connecting NinjaOne
1. In NinjaOne: Administration > Apps > API > Client app IDs > Add. Platform **API Services (machine-to-machine)**, grant type **Client credentials**, scope **Monitoring** (read-only). Copy the Client ID and Client Secret (the secret is shown once).
2. Address by region: `https://app.ninjarmm.com` (US), `https://eu.ninjarmm.com`, `https://ca.ninjarmm.com`, `https://oc.ninjarmm.com`.
3. In the PSA: Integrations > Connect a vendor > NinjaOne.

## Connecting Hudu
1. In Hudu: Admin > API Keys > New. Use a key limited to read access if your plan allows it.
2. Address is your Hudu URL, for example `https://yourcompany.huducloud.com`.
3. Hudu has no built-in warranty field. In the connect form, list **which asset layouts to import** and what kind each is, and name the field that holds the warranty end date:
```json
{"layouts": {"Switches": "network", "Firewalls": "network"},
 "warranty_end_field": "Warranty Expiration"}
```
Layouts not listed are never imported (Hudu also holds documents and applications). Dates may be `YYYY-MM-DD` or `MM/DD/YYYY`. An asset with no date shows **unknown**, never a guess.

## How the data is merged
- **De-duplication:** by normalized serial number within a client. Placeholder serials ("To Be Filled By O.E.M.", "0", "Default string") are ignored. If a serial is missing on either side, the hostname is used instead, but only when it cannot be a different device. The same serial under two clients stays two assets.
- **Precedence per field:** a tech's correction, then the system that owns that class of device (NinjaOne for computers and servers, Hudu for network gear), then the other. A device reported as network by either system is treated as network.
- **Disagreements:** if two systems give different warranty end dates, the owner's value is used and the device shows **sources disagree** so a tech can look.
- **Warranty status** is derived when you look: expired, expiring within 30 / 60 / 90 days, in warranty, or unknown. It is never stored.
- **Retired, not deleted:** a device the vendor stops reporting is marked retired after 30 days (`retire_after_days` in the integration's config). It comes back automatically if it reappears. The database does not let the app delete assets.
- **Corrections survive syncs.** A tech's corrected warranty date (with a reason) is kept separately and always wins; "Undo" returns to the vendor's value. Changes are audited, as are vendor warranty-date changes.
- **A failed sync changes nothing.** If the vendor is down, credentials are bad, or one client's fetch fails, existing data is untouched and the run shows the error. Other clients still sync.

## Sync schedule
The worker (`python -m app.worker`) syncs each enabled integration every 6 hours (`sync_hours` in its config, default 6; NinjaOne itself refreshes warranty weekly so faster gains little). **Sync now** asks the worker, which picks it up within about a minute. A failing integration retries on the same interval, not in a tight loop.

## Credentials and the encryption key
- Vendor credentials are entered in the UI and stored **encrypted (Fernet)** in the database. The key is `CREDENTIALS_KEY` in `.env`, never in the database or repo.
- Credentials are **write-only**: the API and UI never return them, they are redacted from audit snapshots and never logged. The UI shows only "set" and the date.
- **Backups contain only ciphertext.** Restoring a backup without the key yields no usable secrets (you re-enter them). Keep the key in your secret store, **separate from database backups**, and back it up there: if you lose it, you must re-enter every vendor credential.
- Generate a key once: `docker compose run --rm api python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`, put it in `.env` as `CREDENTIALS_KEY=...`, and restart `api` and `worker`.
- **Rotate the key:** set `CREDENTIALS_KEY=<new>,<old>` (new first), restart, run `docker compose exec api python -m app.rekey`, then remove `<old>` and restart again.
- **Rotate a vendor credential:** Integrations > Replace credentials. The old value is overwritten.
- Use a **dedicated read-only** vendor account per system. One per vendor for the whole MSP.

## Client portal "Devices and warranty" (default off)
Two switches must both be on, both admin-only:
1. **Publish to portal** on the client's page (per client).
2. **Show devices** on the contact (per contact; the contact needs portal access first).

The contact then sees a Devices tab: totals, how many expire within 90 days, and a list of name, type, make/model, warranty end and status. **No serial numbers, vendor ids or internal notes.** Withdrawing the publish switch removes access immediately. Denied attempts are logged.

## Permissions
| Action | Who |
|---|---|
| Connect, edit, test, sync, map clients, see credentials status | admin (`integration:manage`) |
| View a client's devices | admin, tech, billing, read-only (`org:read`) |
| Correct a warranty date | admin, tech (`org:write`) |
| Warranty report and CSV | admin, billing (`report:read`) |
| Publish to the portal / flag a contact | admin (`portal:manage`) |

## Not in Phase 1
Vulnerabilities (ConnectSecure), compliance scores, scoring, PTA reports, tickets from findings, warranty-expiry emails, write-back to any vendor. See [VCISO_PLAN.md](VCISO_PLAN.md).

## Decisions taken when building (change them if wrong)
These were assumptions in the plan (section 8). Building went ahead on them being right:
1. NinjaOne and Hudu are single MSP-level accounts with clients inside. If Hudu is per-client instances, the mapping screen needs rework.
2. Hudu warranty lives in a named field on a layout (configured above). Hudu *Expiration* entries are **not** read yet.
3. Where a device is in both systems, NinjaOne wins for computers/servers and Hudu for network gear.
4. Read-only everywhere; no write-back.
5. Warranty data reaches clients only when published per client and flagged per contact.
6. Syncing every 6 hours.
