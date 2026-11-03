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

## Accounting mailbox
Optional. Statements, payment reminders and invoice emails can come from a second mailbox, such as
`accounting@yourmsp.com`. It must be in the same Microsoft 365 tenant. Everything else is still sent from the
support mailbox. Leave the setting empty to send everything from the support mailbox.

The app only sends from the accounting mailbox. It never reads it. So this mailbox gets `Mail.Send` only, and
**no** `Mail.ReadWrite`. Run this in the same Exchange Online PowerShell session as section 3:

```powershell
# The set of mailboxes for accounting mail: exactly one
New-ManagementScope -Name "PSA Accounting Mailbox" `
  -RecipientRestrictionFilter "PrimarySmtpAddress -eq 'accounting@yourmsp.com'"

# Send mail only, limited to that scope
New-ManagementRoleAssignment -App <enterprise-app-object-id> -Role "Application Mail.Send" `
  -CustomResourceScope "PSA Accounting Mailbox"
```

**Verify the scope** (this test bypasses the cache):
```powershell
Test-ServicePrincipalAuthorization -Identity <enterprise-app-object-id> -Resource accounting@yourmsp.com   # Mail.Send: InScope True
Test-ServicePrincipalAuthorization -Identity <enterprise-app-object-id> -Resource someone.else@yourmsp.com # InScope: False
```
Keep the `someone.else` result `False`. It shows the app still cannot reach other mailboxes.
New assignments can take **30 minutes to 2 hours** to take effect.

As in section 2, do **not** add any Mail permissions in Entra ID. They apply to the whole organization and
cancel the scoping.

Last, in the PSA open **Settings → Mail & calendar** and enter the address in **Accounting sender address**.

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
  Each message is sent as a draft we create with our own `Message-ID` (stored on the email row; this needs the
  `Mail.ReadWrite` role above), so a reply whose subject lost the token still threads via In-Reply-To/References.
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
| `The mail app is not allowed to send as accounting@…` | The accounting mailbox scope or its `Application Mail.Send` role assignment is missing or not in effect yet (see [Accounting mailbox](#accounting-mailbox)). The message is marked failed at once, with no retries. It shows on Settings → Mail & calendar and in the audit log. After fixing, re-send it from the notice |

## Calendar sync
The same app can also push appointments to technicians' Outlook calendars and read their busy time for the
dispatch board. That is a separate, optional setup with its own scope (a group of technician mailboxes) and one
more Exchange role, `Application Calendars.ReadWrite`: see `docs/CALENDAR_SETUP.md`. It adds **no** Entra Graph
permission, so the mail scoping above stays intact.

## Reminders and statements
Payment reminders and statements are sent through the same outbox and mailbox, with PDFs attached
(Graph `sendMail` file attachments). They are only sent after a person approves them in Billing > Reminders.
A client who replies creates or updates a ticket like any other email. Sending needs the *Application
Mail.Send* RBAC role above. To send them from a separate accounting address, see [Accounting mailbox](#accounting-mailbox). The review screen refuses to send while the worker reports the mailbox as not configured.

## Staff notifications
The worker also emails the person a ticket is assigned to, using the same mailbox and outbox:
when a ticket is assigned to them (not when they assign it to themselves), when it reaches SLA
**at risk** and again if it **breaches** (once each), and when a customer replies. Emails have the
ticket number, client, priority, status and a link, never the customer's words. Subjects use
`PSA: ticket #10001 ...` (no `[#10001]` token) so replying to one is not mistaken for a customer reply.
Each person can turn any of these off on their profile (click your name); admins can switch the
whole feature off under Settings. Nothing is queued while the mailbox is not configured, so there is
no backlog to flush when you enable it. Unassigned tickets notify nobody (see BACKLOG for a
queue-wide alert).
