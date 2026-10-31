# Verify: client appointment emails, portal appointments and on-call (Phase 5)

Run this once in Phase 15. Use a real mailbox you control as the client contact. The worker must be running
with the mailbox configured. Mark each item pass or fail with a note.

## Client emails
- [ ] Settings: turn on "Email clients about appointments" (it is off by default).
- [ ] Use a ticket whose contact has your test mailbox. Book a client-visible appointment; within about 2-3
  minutes exactly one "booked" email arrives, showing the right time in the business timezone and the tech's
  first name only, with no internal notes.
- [ ] Move the appointment to another time; exactly one "moved" email arrives with the new time.
- [ ] Cancel it; exactly one "cancelled" email arrives, showing the time it was scheduled for and no technician.
- [ ] Book and then move within 2 minutes: one "booked" email with the final time. Book then cancel within 2
  minutes: no email.
- [ ] Book with "Don't email client" ticked: no email. Edit and untick it, move the time: an email follows.
- [ ] Reassign the appointment to another tech without changing the time: no email.
- [ ] A ticket with no contact email but a requester email sends to the requester address.
- [ ] With the switch off, book and move: no email.
- [ ] The notice state (pending, sent, skipped) shown on the appointment matches what happened.

## Portal
- [ ] Give the test contact portal access and sign in at /portal. The Appointments tab lists upcoming ones
  first and past ones (last 30 days) after, with date, time range, tech first name and a ticket link.
- [ ] A cancelled appointment and one not marked client-visible do not appear. A contact without "See all
  company tickets" does not see appointments on a colleague's ticket.
- [ ] A contact with no appointments sees "No appointments scheduled".

## On-call
- [ ] Create a weekly rotation with two or more members, a handoff weekday and time, and an anchor on that
  weekday. "Now" shows the first member; check the next handoff moves to the second.
- [ ] Add an override for another user covering today; "Now" shows the override. Delete it and it reverts.
- [ ] The sidebar widget shows who is on call now, and the dispatch board shades the on-call time.
- [ ] DST spot-check: put a handoff across a clock change (for example Sunday 02:30 or a 09:00 handoff the week
  of the change) and confirm the schedule hands off at the local wall-clock time on both sides.
