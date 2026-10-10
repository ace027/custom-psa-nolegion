# Verify: dispatch board and ticket appointments

## Automated
```sh
service postgresql start >/dev/null 2>&1
scripts/e2e.sh e2e/dispatch.spec.ts                      # throwaway database, API and Vite on free ports
scripts/e2e.sh e2e/dispatch.spec.ts --repeat-each=3
cd frontend && npm run typecheck && npm test && npm run build
```
`scripts/e2e.sh` is described in [DEVELOPMENT.md](../DEVELOPMENT.md). Set `CHROMIUM_PATH` if Playwright's bundled browser is not installed
(in the cloud sandbox: `/opt/pw-browsers/chromium-1194/chrome-linux/chrome`).

The spec pins the clock to Tue 2030-01-08 15:00 UTC (09:00 in America/Chicago, the seeded org zone; it reads the zone from `/api/settings`).
- Booking flow: Book on the ticket, row on the card, Open on board, event in the tech's column, edit 10:00-11:00 to 13:00-14:00, toast, Undo, times back.
- Reassign and conflict: move an appointment onto a tech who is busy at that time; the toast says "Overlaps another appointment" and the block shows the "Has conflicts" icon.
- Drag: mouse-drag an event one hour down; `starts_at` and `ends_at` both move by 60 minutes. Native drag works with Playwright mouse steps, so this test is active (not `fixme`).

Last result (2026-10-09): `scripts/e2e.sh e2e/dispatch.spec.ts --repeat-each=3` => 9 passed (3 tests x 3). `npm run typecheck`, `npm test` (179 passed) and `npm run build` pass.

## Manual: the board (/dispatch)
Sign in as admin@example.com.
1. Day view: one column per active admin/tech, events titled `#number Organization`, "Times in <zone>" badge. Prev, Next, Today and the date box move the day; the URL keeps `view` and `date`.
2. Week view (Week button): one tech at a time (Tech select), Monday to Sunday, in that tech's own zone.
3. Zones: give a tech a different timezone (Profile or schedule settings); in day view hover their event. The tooltip adds "Tech local: HH:mm-HH:mm". Around a DST change the board says "Clocks change today: this day has 23/25 hours."
4. Shading: hours outside the tech's working hours are grey, approved time off is shaded with a "Time off" label, pending time off has its own shade. Shading never blocks clicks or drags.
5. Conflicts: book two techs' overlapping slots, or book outside working hours or in time off. The block shows the warning icon and a red outline; the toast and tooltip name each conflict. Nothing is blocked.
6. Book: click an empty slot (or New booking), search a ticket, pick a tech and times, Book. The toast offers Undo, which cancels the booking.
7. Edit: click an event, change tech, times or notes, Save. The toast shows the change (e.g. "Terry Tech, Tue 14:00") with Undo. Cancel appointment asks for confirmation.
8. Drag and resize an event; the change saves at once and Undo reverses it. A failed save snaps the block back and shows an alert.
9. View only: sign in as readonly@example.com. The board shows a "View only" badge, no New booking, no drag, and the edit dialog has disabled fields and only Close.

## Manual: the ticket card
1. Open a ticket as admin@example.com. Below Time there is an Appointments card. It lists the ticket's appointments by start time, in the browser's zone with a zone suffix, with the tech name.
2. Book (hidden when the ticket is closed or has no organization): the dialog opens with the ticket fixed. After booking, the row appears.
3. Upcoming rows with a conflict show "Has conflicts"; past rows never do. Open on board goes to `/dispatch?view=day&date=YYYY-MM-DD`.
4. Start timer (on upcoming or ongoing rows): choose a Work type, Start. The running-timer bar appears with the note "Appointment YYYY-MM-DD". Starting a second one shows the API's "already running" message.
5. As readonly@example.com the card lists appointments with no Book or Start timer.
