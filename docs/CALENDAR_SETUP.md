# Outlook calendar sync setup (Microsoft Graph)

The **worker** can copy each scheduled appointment to the assigned technician's Outlook calendar, and can read
each technician's Outlook busy time so the dispatch board shows it. It reuses the app registration from
`docs/MAIL_SETUP.md` (the `PSA Mail` app and its client secret). **No Graph permission is added in Entra ID.**
The only change is two more Exchange RBAC role assignments, limited to a group of technician mailboxes.

> Same warning as the mail connector: a Graph *application* permission for calendars granted in Entra
> reaches **every mailbox in the tenant** and cancels the scoping below. Grant the access in Exchange only.

## What syncs
- **One way, PSA to Outlook.** The PSA is the source of truth. Editing or moving the event in Outlook changes
  nothing in the PSA, and the next push overwrites your edit. Deleting the event in Outlook does not cancel the
  appointment, and the event is recreated the next time the appointment is pushed.
- Reschedules, reassignments (the event moves to the new tech's calendar) and cancellations are pushed too.
- **Event contents:** subject `PSA #<ticket id> appointment`, a body that is only a link to the ticket
  (`<PUBLIC_URL>/tickets/<ticket id>`), marked **private** and shown as busy. The client name, ticket subject,
  notes and address are never sent.
- **Busy time, the other way:** the worker asks Graph `getSchedule` every **5 minutes** for each active user who can
  write the schedule and has an email address, from 1 day back to 14 days ahead. Only start, end and status are
  stored, never meeting subjects. The board shows these as teal hatched blocks, informational only: they do not
  block booking and do not change free time. The board says how old the data is, and warns when it is
  **older than 15 minutes** or has never loaded.
- Past appointments are not pushed (they show "Not synced: past appointment").

## 1. A group of technician mailboxes
The scope is a **mail-enabled security group**, so adding or removing a technician needs no PowerShell.
Exchange admin center, Recipients, Groups, Mail-enabled security, Add a group named `PSA Techs`, and add every
technician (and admin who takes appointments) as a member. Or in PowerShell:

```powershell
Connect-ExchangeOnline
New-DistributionGroup -Name "PSA Techs" -Alias psatechs -Type Security -Members tech1@yourmsp.com,tech2@yourmsp.com
```

## 2. Scope the app to that group (Exchange Online PowerShell)
Requires the Organization Management role group. The service principal already exists if you did the mail setup
(otherwise run `New-ServicePrincipal` as in `docs/MAIL_SETUP.md` section 3).

```powershell
$group = Get-DistributionGroup "PSA Techs"

# The set of mailboxes the app may touch: members of the group
New-ManagementScope -Name "PSA Techs Calendars" `
  -RecipientRestrictionFilter "MemberOfGroup -eq '$($group.DistinguishedName)'"

# Read and write calendars (events and getSchedule), limited to that scope
New-ManagementRoleAssignment -App <enterprise-app-object-id> -Role "Application Calendars.ReadWrite" `
  -CustomResourceScope "PSA Techs Calendars"
```

**Verify the scope, both directions** (this test bypasses the cache):
```powershell
Test-ServicePrincipalAuthorization -Identity <enterprise-app-object-id> -Resource tech1@yourmsp.com        # InScope: True
Test-ServicePrincipalAuthorization -Identity <enterprise-app-object-id> -Resource someone.else@yourmsp.com # InScope: False
```
New assignments can take **30 minutes to 2 hours** to take effect. Group membership changes can take a similar
time to reach the scope.

## 3. Try it against the real tenant before switching it on
`backend/dev/graph_calendar_spike.py` uses the same Graph client as the worker and the credentials in your `.env`
(`GRAPH_TENANT_ID`, `GRAPH_CLIENT_ID`, `GRAPH_CLIENT_SECRET`). Run it from `backend/`:

```bash
# Read-only: asks for the mailbox's busy time and creates nothing
python dev/graph_calendar_spike.py --mailbox tech1@yourmsp.com

# Also creates a test event, creates it again (must return the same event), moves it, then deletes it
python dev/graph_calendar_spike.py --mailbox tech1@yourmsp.com --write

# Also checks the boundary: a mailbox outside the group must be refused
python dev/graph_calendar_spike.py --mailbox tech1@yourmsp.com --write --outside someone.else@yourmsp.com
```

**What PASS looks like.** Each step prints a line, then a `== SPIKE SUMMARY ==` block repeats them:
`PASS getSchedule read`, and with `--write`: `PASS create_event`, `PASS idempotent create`, `PASS update_event`,
`PASS delete_event`, `PASS delete again tolerated (404)`; with `--outside`: `PASS RBAC boundary` (denied with 403).
The exit code is 0 when nothing says `FAIL`. Any `FAIL` line includes the HTTP status; see Troubleshooting. Send
the final block to whoever owns the setup. The test event is removed again; the client secret and token are never printed.

## 4. Switch it on
Sign in as an admin, open **Settings**, find **Outlook calendar sync**, and tick the box. Until then nothing is
sent and nothing is polled; appointments booked meanwhile wait as pending and are pushed once it is on.
The card shows how many pushes are waiting or failed and how old the busy cache is. Within about 5 minutes the
dispatch board shows "Outlook busy updated N min ago". Switching it off stops both jobs and leaves existing
events in Outlook.

## Troubleshooting
| Symptom | Likely cause |
|---|---|
| Spike or sync fails with **403** (`ErrorAccessDenied`) | The mailbox is not in the `PSA Techs` group (the scope), the role assignment is not applied yet (wait up to 2 h), or the wrong Object ID was used. `Test-ServicePrincipalAuthorization` shows `InScope: False` |
| Board says "Outlook busy not loaded yet" | Sync was just switched on (wait 5 minutes), the worker is not running (Settings shows the mailbox card's *Worker last seen*), or every fetch failed (see *Busy fetch errors* on the card) |
| Board says "may be out of date" | Last good fetch is more than 15 minutes old: worker stopped, or Graph returning errors. The old blocks stay visible meanwhile |
| A technician has no busy time | Their role cannot write the schedule, they have no email, or they are not in the group |
| Appointment shows **Outlook sync failed** | Open the appointment (or the red "N Outlook sync failures" chip on the board) to read the error, fix the cause (usually a 403 above), then press **Retry Outlook sync**. A 409 means someone already retried it |
| Event edited or deleted in Outlook | By design the PSA wins: the next push overwrites or recreates it. Change the appointment in the PSA instead |
| `token request failed: 401` | Wrong tenant or client id, or the client secret expired (same app as the mail connector) |
