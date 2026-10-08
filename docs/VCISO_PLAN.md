# vCISO platform and asset intelligence: plan

Status: **Phase 1 is BUILT** (see [INTEGRATIONS.md](INTEGRATIONS.md) for how it works and what differs from this plan). **Phases 2 to 5 are plan only.**
Sections marked **(assumption)** were not confirmed and should be checked before building.

## 1. Goal
Give clients a sleek, professional view of their security posture and hardware health, fed
automatically from the tools you already run, with frozen point-in-time reports (PTAs) for
audits, insurers and quarterly reviews. Techs work in the PSA; clients see a curated view in
the portal.

Sources, in the order we will add them:
1. **NinjaOne**: warranty and inventory for computers and servers.
2. **Hudu**: warranty and inventory for network equipment (and anything else you document there).
3. **ConnectSecure**: vulnerabilities, remediation, score history. *Details pending from you.*
4. **Compliance Scorecard**: CMMC/NIST scores and control status. *No public API found; pending their answer.*

## 2. Principles (same as the rest of the PSA)
- **Read-only toward vendors.** The PSA pulls; it never changes anything in NinjaOne, Hudu, ConnectSecure or Compliance Scorecard.
- **Nothing reaches a client without a person publishing it.** Sharing is per client, off by default.
- **One neutral model.** Vendors are adapters; dashboards read only the PSA's own tables, so a vendor can be swapped or added without touching the UI.
- **Multi-tenant safe.** Every new client-owned table has `organization_id`, forced row-level security, and is covered by the existing guard test.
- **Least privilege and audit.** Vendor API accounts are read-only; every configuration change, sync failure, override, publish and portal view of sensitive data is auditable.
- **Manual judgment survives syncs.** A tech's override or accepted-risk note is never overwritten by the next sync.
- **Honest data.** Every record shows its source and when it was last synced; stale data is flagged, never shown as current.
- **Minimal dependencies.** One new library at most (encryption), and only if not already present.

## 3. Architecture

### 3.1 Connector framework
- A small internal interface: *test connection*, *list vendor clients*, *fetch inventory / findings for one vendor client*.
- One adapter per vendor. Adapters return plain data; a single sync service normalizes, de-duplicates and writes.
- The existing **worker** runs syncs on a schedule (default every 6 hours, configurable, plus a "sync now" button). A run is recorded (start, end, counts, error) and is safe to repeat.
- Failure handling: rate limits and outages back off and retry next cycle. **A failed or partial sync never deletes or blanks data.** Assets not seen for N days (default 30) are marked *retired*, not removed.
- A connector with bad credentials shows a clear red status in Settings and in the mailbox-style health card.

### 3.2 Credentials and secrets (the biggest decision)
Today the PSA keeps secrets only in environment variables. Vendor credentials need to be entered in the UI, so they must be stored.
- Proposed: encrypt each credential with an application key held in the environment / secret store (never in the database or repo); store only ciphertext.
- Credentials are write-only in the API and UI (shown as "set" / "last changed"), never returned, never logged, redacted in audit snapshots.
- Rotation: replace in the UI; the old value is overwritten. Key rotation gets a documented procedure (re-encrypt job).
- Admin-only (`integration:manage`); backups contain only ciphertext, so restoring a backup without the key yields no usable secrets. Document this in BACKUP_RESTORE.md.
- Vendor accounts should be **dedicated, read-only** API users, one per vendor for the whole MSP **(assumption: NinjaOne and Hudu are single MSP-level accounts with clients inside)**.

### 3.3 Mapping vendor clients to PSA clients
- After connecting, the PSA lists the vendor's organizations/companies. A mapping screen matches each to a PSA organization (suggested by name), or marks it *ignored*.
- Unmapped vendor clients are shown as a to-do, never guessed. New vendor clients that appear later are flagged.

## 4. Data model (Phase 1: asset inventory and warranty)
All client-owned tables carry `organization_id` with forced RLS.

| Table | Purpose |
|---|---|
| `integrations` | One row per connected vendor: kind (`ninjaone`, `hudu`, later others), name, base URL, encrypted credentials, enabled, status, last sync, last error. Not client-owned (MSP-level). |
| `integration_client_maps` | Vendor client id/name to PSA organization (or ignored). |
| `sync_runs` | History of each sync: counts added/changed/retired, duration, error. |
| `assets` | The canonical device record: organization, kind (computer, server, network, other), name, manufacturer, model, serial, warranty start/end, last seen, first seen, retired at. |
| `asset_sources` | Links an asset to each vendor record that describes it (integration, external id, last synced, a hash to detect change). |
| `asset_overrides` | A tech's manual correction (for example a warranty end date the vendor got wrong), with reason, author and date. Wins over synced values. |

Rules:
- **De-duplication key:** normalized serial number; fallback to hostname within the client. Devices in both systems merge into one asset with two sources; conflicts are shown to a tech, not silently resolved.
- **Field precedence:** manual override, then the system that owns that class of device (NinjaOne for computers/servers, Hudu for network gear), then the other.
- **Warranty status** is derived, never stored: *expired*, *expiring in 30 / 60 / 90 days*, *in warranty*, *unknown* (no date).
- History: warranty-date changes are audited so "who changed this and why" is answerable.

## 5. Phase 1: warranty and inventory (approved as first)

### 5.1 Scope
1. Connector framework, encrypted credential storage, mapping screen, sync worker (3.1 to 3.3).
2. **NinjaOne adapter.** It exposes device warranty start and end dates through its public API using OAuth client credentials **(verified in vendor docs; exact endpoints and pagination to be confirmed in the first build step)**. Also imports name, manufacturer/model, serial and last-contact time.
3. **Hudu adapter.** Assets come from its REST API. Warranty in Hudu is not a built-in field: it is usually a custom field or an *Expiration* entry **(assumption; needs confirming with how you record it today)**. The adapter maps a configurable field name to warranty end date.
4. Staff UI: Settings > Integrations (connect, test, sync now, status); a per-client **Assets** tab; a cross-client **Warranty** report (expiring/expired, filter by client and window) with CSV export under the existing `report:read` permission.
5. Client view (optional per client, default off): a **Devices and warranty** page in the portal for designated contacts: total devices, count expiring in 90 days, a clean list, and a "refresh planning" summary. A tech publishes it per client; portal contacts need an explicit flag (like `portal_org_tickets`) to see it.

### 5.2 Not in Phase 1
Vulnerability data, compliance scores, scoring, PTA PDFs, tickets from findings, write-back to any vendor, warranty-expiry alert emails (backlog).

### 5.3 Permissions (new)
- `integration:manage` (admin): connect vendors, change credentials, mapping.
- Assets read: with `org:read` (techs need it). Manual override: `org:write`.
- Warranty report/CSV: `report:read` (admin, billing).
- Portal visibility: a per-client publish switch plus a per-contact flag, both admin-controlled.

### 5.4 Testing approach
- Fake vendor servers (as with the Graph client) so no test touches a real API.
- Tests for: sync idempotency, failed-sync-changes-nothing, retire-not-delete, de-dup and conflict handling, override survives sync, mapping never guesses, secrets never in any API response, log line or audit row, RLS isolation, permission matrix, portal exposure limited to designated contacts, and contract coverage of every route.

### 5.5 Phase 1 acceptance
Connect NinjaOne and Hudu with read-only accounts, map clients, and see a correct, de-duplicated device list with warranty status for a real client; a tech override survives the next sync; a client contact you designate sees only their own devices; a forced sync failure leaves data intact and shows a clear error.

## 6. Later phases (outline, each planned in detail before starting)
- **Phase 2: ConnectSecure.** Same framework. Findings with a life cycle (first seen, last seen, resolved), severity normalized to a common scale, suppressions/accepted risk that survive syncs, daily score snapshots for trends. Rough source data (per third-party connector docs): devices, per-asset vulnerabilities, remediation plans, suppressions; auth by client id/secret plus customer id. **Blocked until you supply the account details/API docs.**
- **Phase 3: vCISO dashboard and PTA.** Portal dashboard (score, top risks, trend, remediation progress, warranty), and a frozen branded **PTA** PDF generated on demand or quarterly, stored immutably like statements. Needs a deliberate visual design pass.
- **Phase 4: Compliance Scorecard.** Depends entirely on what they expose: API pull, scheduled report ingest, or a link-out/SSO to their portal.
- **Phase 5: roadmap and workflow.** Remediation roadmap, risk register, accepted-risk approvals, findings to tickets and billable work, QBR pack, expiry/alert emails.

## 7. Risks and "you might regret this later" flags
1. **Secret storage.** Hardest to change later. Needs your explicit approval of the approach in 3.2.
2. **Vendor API drift.** Third-party APIs change; adapters are isolated and covered by fake-server tests so breakage is caught in one place.
3. **Data quality.** Warranty data is often missing or wrong. The design shows "unknown" rather than guessing, and allows overrides, but expect clean-up work per client.
4. **Compliance Scorecard may have no API.** Phase 4 scope could shrink to a link-out.
5. **Sensitive data.** Vulnerability data is the most damaging thing to leak. It gets its own portal flag and per-client publish gate, and portal sessions stay scoped to one client.
6. **Scope creep.** vCISO is a large product. Phases are sized so each ends with working, tested software you can use.

## 8. Assumptions to confirm before building Phase 1
1. NinjaOne and Hudu are single MSP-level accounts with clients inside. (If Hudu is per-client instances, mapping changes.)
2. In Hudu, warranty is recorded as a custom field or an Expiration; tell us which and the field name.
3. Network gear may be in NinjaOne too (SNMP devices); if so, which system wins.
4. Read-only everywhere; no write-back.
5. Warranty data is shown to clients only after a tech publishes it per client, and only to designated contacts.
6. Syncing every 6 hours is fine (NinjaOne itself refreshes warranty weekly, so more often gains little).

## 9. Decisions needed from you
- Approve the secret-storage approach (3.2).
- Confirm or correct assumptions in section 8.
- Say "go" to start Phase 1; ConnectSecure work waits for your account details.
