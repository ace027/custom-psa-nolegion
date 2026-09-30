# Email-to-ticket setup (Microsoft Graph)

The **worker** container polls one shared mailbox every 60 seconds, turns new mail into tickets or ticket
replies, and sends the customer-visible notes you choose to email. It uses the Microsoft Graph API with
*application* permissions, so it works without a signed-in user.

> **Read this first:** by default, an app with `Mail.ReadWrite`/`Mail.Send` *application* permissions can
> read and send as **every mailbox in your tenant**. This setup uses **Exchange RBAC for Applications** to
> limit the app to the ONE support mailbox, and grants **no** mail permissions in Entra ID at all.
> Microsoft's docs call Application Access Policies "legacy" and say new configuration should not use them
> ([RBAC for Applications](https://learn.microsoft.com/exchange/permissions-exo/application-rbac)).

## 1. The mailbox
Create a **shared mailbox** such as `support@yourmsp.com` (Exchange admin center → Recipients → Mailboxes →
Add a shared mailbox). Point your public support address / mail flow at it.

## 2. A separate app registration
Use a **different** app registration from the sign-in one (`docs/ENTRA_SETUP.md`), so each has its own
secret and blast radius.

Entra admin center → App registrations → New registration → name `PSA Mail`, single tenant, no redirect URI.
Then **Certificates & secrets → New client secret** (calendar a reminder before it expires).

**Do NOT add any Microsoft Graph API permissions** (no `Mail.Read`, `Mail.ReadWrite`, `Mail.Send`). Permissions
consented in Entra are organization-wide and are *added to* the scoped Exchange grants, which would cancel
the scoping ("the union results in no effective resource scoping").

Note two IDs (Entra → **Enterprise applications** → PSA Mail, *not* the App registrations page, which shows a
different Object ID):
- **Application (client) ID**
- **Object ID** of the enterprise application (service principal)

## 3. Scope the app to the one mailbox (Exchange Online PowerShell)
Requires the Organization Management role group. Run:

```powershell
Connect-ExchangeOnline

# Exchange's pointer to the Entra service principal
New-ServicePrincipal -AppId <client-id> -ObjectId <enterprise-app-object-id> -DisplayName "PSA Mail"

# The set of mailboxes the app may touch: exactly one
New-ManagementScope -Name "PSA Support Mailbox" `
  -RecipientRestrictionFilter "PrimarySmtpAddress -eq 'support@yourmsp.com'"

# Read/update/mark-read mail, and send mail, both limited to that scope
New-ManagementRoleAssignment -App <enterprise-app-object-id> -Role "Application Mail.ReadWrite" `
  -CustomResourceScope "PSA Support Mailbox"
New-ManagementRoleAssignment -App <enterprise-app-object-id> -Role "Application Mail.Send" `
  -CustomResourceScope "PSA Support Mailbox"
```

**Verify the scope, both directions** (this test bypasses the cache):
```powershell
Test-ServicePrincipalAuthorization -Identity <enterprise-app-object-id> -Resource support@yourmsp.com    # InScope: True
Test-ServicePrincipalAuthorization -Identity <enterprise-app-object-id> -Resource someone.else@yourmsp.com  # InScope: False
```
Keep that second result in your compliance evidence: it shows least privilege for the mail connector.
New assignments can take **30 minutes to 2 hours** to take effect.

## 4. Configure the PSA
In `.env` (never commit it):
```
GRAPH_TENANT_ID=<directory (tenant) id>
GRAPH_CLIENT_ID=<application (client) id of PSA Mail>
GRAPH_CLIENT_SECRET=<the secret value>
MAIL_MAILBOX=support@yourmsp.com
```
GCC High / other sovereign clouds: also set `GRAPH_BASE_URL=https://graph.microsoft.us/v1.0` and
`GRAPH_LOGIN_URL=https://login.microsoftonline.us`.

Then `docker compose up -d worker`. Open **Settings → Mailbox connector** in the PSA: it should show
*Working*, the worker's last-seen time, and the last poll. Send a test email to the mailbox.

## How it behaves (so nothing surprises you)
| Situation | What happens |
|---|---|
| Email from a known contact | New ticket for that contact's organization |
| Sender not a contact, but their **domain** belongs to exactly one organization | New ticket for that organization (no contact set) |
| Unknown sender, freemail domain (gmail.com, outlook.com, …), several matching contacts/organizations | New ticket with **no organization** → *Needs triage* (dashboard + Tickets filter). Assign the organization once; notes/attachments follow it. Time cannot be logged until then |
| Reply containing `[#10234]` in the subject, or matching reply headers | Added to that ticket as a customer-visible note; a waiting/resolved/closed ticket reopens and its SLA clock resumes |
| Reply with a valid ticket number **from someone who is not a known contact of that ticket** | Not attached (ticket numbers are guessable). A new *Needs triage* ticket is created that mentions the number |
| Auto-replies, out-of-office, bounces, bulk mail, mail from the mailbox itself, `no-reply` senders | Ignored and recorded (prevents mail loops) |
| Quoted history (`On … wrote:`, `-----Original Message-----`, `>` lines) | Trimmed from the note; the full original is kept in the database |
| Attachments | Saved to the `attachments` volume (max 10 MB each; larger ones are skipped) and offered as downloads only, never displayed inline |

- **Plain text only.** The PSA asks Graph for the text version of each message and never renders HTML from
  email, so there is no HTML-injection or tracking-pixel exposure.
- **Sending**: emailing a customer-visible note queues it; the worker sends it as the shared mailbox with the
  ticket number in the subject `[#10234]`, so replies thread back automatically. Failed sends retry for
  5 cycles, then show as *failed* (audit log: `email.send_failed`; Settings shows the count).
- **No automatic acknowledgement email** is sent (avoids loops); it's in `docs/BACKLOG.md`.
- **Spoofing**: the PSA trusts the `From` address that Exchange Online delivered. Keep your Microsoft 365
  anti-spoofing (SPF/DKIM/DMARC enforcement) enabled; that is what stops a forged `From` header, not the PSA.
- **A message the PSA cannot process** stays unread in the inbox, is retried every cycle, and is counted in
  the connector's *last error*. Fix the cause, or move the message out of the Inbox to unblock it.

## Troubleshooting
| Symptom | Likely cause |
|---|---|
| Settings shows worker *never seen* | Worker container isn't running: `docker compose logs worker` |
| `token request failed: 401` | Wrong tenant/client id, or the client secret expired |
| `403 ErrorAccessDenied` / `Access to OData is disabled` | Scope not applied yet (wait up to 2 h), wrong Object ID used in `New-ServicePrincipal`, or the mailbox address in `.env` doesn't match the scope filter |
| Mail arrives but nothing is ingested | Message already read (only *unread* mail is polled), or it is in a sub-folder (only the Inbox is polled) |
| Sends fail with 403 | `Application Mail.Send` role assignment missing |
