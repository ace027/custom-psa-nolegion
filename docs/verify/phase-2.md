# Phase 2: what to verify manually

Prep: dev stack with seed data (`docs/DEVELOPMENT.md`) as `admin@example.com` and `tech@example.com`.
For the email items you need EITHER a real mailbox (`docs/MAIL_SETUP.md`) OR the local fake Graph
(`backend/dev/fake_graph.py`, see DEVELOPMENT.md).

## Tickets
- [ ] Dashboard shows counts, "SLA at risk or breached", "My open tickets", "Unassigned"
- [ ] Create a ticket (Tickets → New ticket): number starts at 10001, queue/priority defaulted
- [ ] Assigning a *New* ticket to someone moves it to *Open*
- [ ] Filters work: status, queue, assignee (Me / Unassigned), open only, needs triage, search by subject or `#number`
- [ ] Status changes: Resolved and Closed stamp times; setting it back to Open clears them

## Notes and time
- [ ] Internal notes are yellow and labelled "internal note"; customer-visible ones are white
- [ ] First customer-visible note marks "First response due … (met)"; an internal note does not
- [ ] "Email it to the customer" queues a message (status *pending* → *sent* within a minute once the worker runs)
- [ ] Log 20 minutes: *Actual 20 min, Billable 30 min* (rounds **up** to the 15-minute increment); non-billable shows 0
- [ ] You can void your own time entry but not someone else's (admin can void anyone's)

## SLA
- [ ] Settings → Business hours are correct for you (time zone, days, open/close)
- [ ] Set a priority's first-response target to a few minutes on a test ticket: it turns *SLA at risk* then *breached* and shows on the dashboard
- [ ] Status *Waiting on customer* shows *SLA paused*; moving it back to Open resumes it (due date moves later by the business time paused)
- [ ] Resolved tickets show no SLA badge

## Email (real mailbox or fake Graph)
- [ ] Mail from a known contact → ticket for the right organization and contact, quoted history trimmed
- [ ] Mail from an unknown sender → *Needs triage* ticket; assigning an organization works, and only once
- [ ] Customer replies to your emailed note → appears on the same ticket as an emailed customer note; a resolved ticket reopens
- [ ] Out-of-office / bounce / your own address → no ticket
- [ ] Attachment appears on the ticket and downloads as a file (doesn't open in the browser)
- [ ] Settings → Mailbox connector shows *Working* and a recent "worker last seen"

## Roles and security
- [ ] `read_only` and `billing` can see tickets, notes and time but have no add/edit controls
- [ ] `tech` can work tickets but has no Settings link; `admin` can edit queues, categories, priorities, work types, hours
- [ ] Audit log has rows for ticket create/update, notes, time entries and settings changes, with before/after values
- [ ] (Real mailbox) `Test-ServicePrincipalAuthorization` shows `InScope: True` for the support mailbox and `False` for another mailbox

## Ops
- [ ] `docker compose up -d --build` starts `worker` alongside the rest (verified in the dev sandbox; check on your VM)
- [ ] Run `deploy/backup.sh`: it writes both `*.dump.age` and `*.attachments.tar.age`; do the restore drill from `docs/BACKUP_RESTORE.md`
