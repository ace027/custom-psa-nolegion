import type { Appointment, AvailabilityRow, ConflictKind, StaffUser } from "./api";
import { ageMinutes, backgroundBlocks, conflictLabel, dropPatch, isStale, moveSummary, oldestFetch, toEvents, toResources, undoPatch } from "./board";
import { toBoardDate } from "./zone";

const CHI = "America/Chicago";
// Monday 2030-01-07: Chicago 09:00 is 15:00Z
const appt = (over: Partial<Appointment> = {}): Appointment => ({
  id: 1,
  organization_id: 1,
  organization_name: "Acme",
  ticket_id: 5,
  ticket_number: 101,
  ticket_subject: "Printer",
  tech_id: 10,
  tech_name: "Sam",
  starts_at: "2030-01-07T15:00:00Z",
  ends_at: "2030-01-07T16:00:00Z",
  status: "scheduled",
  notes: null,
  client_visible: true,
  created_by: null,
  cancelled_at: null,
  cancel_reason: null,
  conflicts: [],
  sync: { state: "off", last_error: null },
  ...over,
});
const staff: StaffUser[] = [
  { id: 10, display_name: "Sam", role: "tech" },
  { id: 11, display_name: "Alex", role: "admin" },
];
const board = (iso: string) => toBoardDate(iso, CHI);
const target = (a: Appointment, over: Partial<{ start: Date; end: Date; resourceId: number }> = {}) => ({
  start: board(a.starts_at),
  end: board(a.ends_at),
  resourceId: a.tech_id,
  ...over,
});

describe("toEvents / toResources", () => {
  it("maps appointments to board events in the board zone", () => {
    const a = appt({ conflicts: [{ kind: "overlap", time_off_id: null, appointment_id: 2 }] });
    const [e] = toEvents([a], CHI);
    expect(e).toMatchObject({ id: 1, title: "#101 Acme", resourceId: 10, conflicts: a.conflicts, appointment: a });
    expect(e.start.getHours()).toBe(9);
    expect(e.end.getHours()).toBe(10);
  });
  it("copes with missing ticket or client names", () => {
    expect(toEvents([appt({ organization_name: null })], CHI)[0].title).toBe("#101");
  });
  it("maps staff to resources", () => {
    expect(toResources(staff)).toEqual([
      { id: 10, title: "Sam" },
      { id: 11, title: "Alex" },
    ]);
  });
});

describe("dropPatch / undoPatch", () => {
  const a = appt();
  it("returns null when nothing changed, even if the server wrote +00:00", () => {
    expect(dropPatch(a, target(a), CHI)).toBeNull();
    const b = appt({ starts_at: "2030-01-07T15:00:00+00:00", ends_at: "2030-01-07T16:00:00+00:00" });
    expect(dropPatch(b, target(b), CHI)).toBeNull();
  });
  it("patches only the tech on a reassign", () => {
    expect(dropPatch(a, target(a, { resourceId: 11 }), CHI)).toEqual({ tech_id: 11 });
  });
  it("patches both times on a move in time", () => {
    const t = target(a, { start: board("2030-01-08T20:00:00Z"), end: board("2030-01-08T21:00:00Z") });
    expect(dropPatch(a, t, CHI)).toEqual({ starts_at: "2030-01-08T20:00:00.000Z", ends_at: "2030-01-08T21:00:00.000Z" });
  });
  it("patches tech and times together", () => {
    const t = target(a, { start: board("2030-01-07T17:00:00Z"), end: board("2030-01-07T18:00:00Z"), resourceId: 11 });
    expect(dropPatch(a, t, CHI)).toEqual({ tech_id: 11, starts_at: "2030-01-07T17:00:00.000Z", ends_at: "2030-01-07T18:00:00.000Z" });
  });
  it("a resize changes only ends_at", () => {
    const t = target(a, { end: board("2030-01-07T17:30:00Z") });
    expect(dropPatch(a, t, CHI)).toEqual({ ends_at: "2030-01-07T17:30:00.000Z" });
  });
  it("undoPatch restores the original tech and times", () => {
    const t = target(a, { start: board("2030-01-07T17:00:00Z"), end: board("2030-01-07T19:00:00Z"), resourceId: 11 });
    const patch = dropPatch(a, t, CHI)!;
    const after = appt({ tech_id: 11, starts_at: patch.starts_at!, ends_at: patch.ends_at! });
    const undo = undoPatch(a, after);
    expect(undo).toEqual({ tech_id: 10, starts_at: "2030-01-07T15:00:00.000Z", ends_at: "2030-01-07T16:00:00.000Z" });
    // applying the undo to `after` gives back `a`, so dropping onto a's own slot is a no-op
    const restored = appt({ ...undo });
    expect(dropPatch(a, target(restored), CHI)).toBeNull();
  });
});

describe("backgroundBlocks", () => {
  // Chicago day 2030-01-07 is 06:00Z to 06:00Z next day. Split shift 08:00-12:00 and 13:00-17:00 local.
  const range = { from: "2030-01-07T06:00:00.000Z", to: "2030-01-08T06:00:00.000Z" };
  const row: AvailabilityRow = {
    user_id: 10,
    timezone: CHI,
    working: [
      { starts_at: "2030-01-07T14:00:00Z", ends_at: "2030-01-07T18:00:00Z" },
      { starts_at: "2030-01-07T19:00:00Z", ends_at: "2030-01-07T23:00:00Z" },
    ],
    time_off: [{ starts_at: "2030-01-07T15:00:00Z", ends_at: "2030-01-07T16:00:00Z" }],
    time_off_pending: [{ starts_at: "2030-01-07T20:00:00Z", ends_at: "2030-01-07T21:00:00Z" }],
    appointments: [],
    free: [],
    outlook_busy: [],
    outlook_fetched_at: null,
  };
  const hm = (b: { start: Date; end: Date }) => [b.start.getHours(), b.end.getHours()];

  it("shades the gaps between working windows as off-hours", () => {
    const off = backgroundBlocks([row], CHI, range).filter((b) => b.kind === "off_hours");
    expect(off.map(hm)).toEqual([
      [0, 8],
      [12, 13],
      [17, 0], // to midnight, which is the next day 00:00
    ]);
    expect(off[2].end.getDate()).toBe(8);
    expect(off.every((b) => b.resourceId === 10)).toBe(true);
  });
  it("adds approved and pending time off as their own kinds", () => {
    const blocks = backgroundBlocks([row], CHI, range);
    expect(blocks.filter((b) => b.kind === "time_off").map(hm)).toEqual([[9, 10]]);
    expect(blocks.filter((b) => b.kind === "time_off_pending").map(hm)).toEqual([[14, 15]]);
  });
  it("shades the whole range off-hours when there are no working windows", () => {
    const blocks = backgroundBlocks([{ ...row, working: [], time_off: [], time_off_pending: [] }], CHI, range);
    expect(blocks).toHaveLength(1);
    expect(blocks[0]).toMatchObject({ kind: "off_hours", resourceId: 10 });
  });
  it("clips blocks to the visible range", () => {
    const wide = { ...row, working: [], time_off: [{ starts_at: "2030-01-06T00:00:00Z", ends_at: "2030-01-09T00:00:00Z" }], time_off_pending: [] };
    const [off] = backgroundBlocks([wide], CHI, range).filter((b) => b.kind === "time_off");
    expect(off.start).toEqual(board(range.from));
    expect(off.end).toEqual(board(range.to));
  });
  it("adds Outlook busy time as its own kind with the status", () => {
    const withBusy = { ...row, outlook_busy: [{ starts_at: "2030-01-07T17:00:00Z", ends_at: "2030-01-07T18:00:00Z", status: "tentative" }] };
    const blocks = backgroundBlocks([withBusy], CHI, range).filter((b) => b.kind === "outlook");
    expect(blocks.map(hm)).toEqual([[11, 12]]);
    expect(blocks[0].status).toBe("tentative");
  });
  it("converts an Outlook block across the spring DST change", () => {
    // Chicago clocks jump 02:00 -> 03:00 on 2030-03-10 (08:00Z). 07:00Z-10:00Z is 01:00 CST to 05:00 CDT.
    const day = { from: "2030-03-10T06:00:00.000Z", to: "2030-03-11T05:00:00.000Z" };
    const dst = { ...row, working: [{ starts_at: "2030-03-10T14:00:00Z", ends_at: "2030-03-10T22:00:00Z" }], time_off: [], time_off_pending: [], outlook_busy: [{ starts_at: "2030-03-10T07:00:00Z", ends_at: "2030-03-10T10:00:00Z", status: "busy" }] };
    const [b] = backgroundBlocks([dst], CHI, day).filter((x) => x.kind === "outlook");
    expect(hm(b)).toEqual([1, 5]);
    expect(b.start.getDate()).toBe(10);
  });
  it("clips Outlook blocks to the range", () => {
    const wide = { ...row, outlook_busy: [{ starts_at: "2030-01-06T00:00:00Z", ends_at: "2030-01-09T00:00:00Z", status: "busy" }] };
    const [b] = backgroundBlocks([wide], CHI, range).filter((x) => x.kind === "outlook");
    expect(b.start).toEqual(board(range.from));
    expect(b.end).toEqual(board(range.to));
  });
  it("keeps techs apart", () => {
    const blocks = backgroundBlocks([row, { ...row, user_id: 11 }], CHI, range);
    expect(new Set(blocks.map((b) => b.resourceId))).toEqual(new Set([10, 11]));
  });
});

describe("conflictLabel", () => {
  it.each<[ConflictKind, string]>([
    ["outside_hours", "Outside working hours"],
    ["time_off", "During approved time off"],
    ["time_off_pending", "During pending time off"],
    ["overlap", "Overlaps another appointment"],
  ])("%s", (kind, label) => {
    expect(conflictLabel(kind)).toBe(label);
  });
});

describe("moveSummary", () => {
  const a = appt();
  const sum = (after: Appointment) => moveSummary(a, after, staff, CHI);
  it("names a reassign", () => expect(sum(appt({ tech_id: 11 }))).toBe("Moved to Alex"));
  it("names a reschedule", () => {
    // Tuesday 2030-01-08 14:00 Chicago is 20:00Z
    expect(sum(appt({ starts_at: "2030-01-08T20:00:00Z", ends_at: "2030-01-08T21:00:00Z" }))).toBe("Rescheduled to Tue 14:00");
  });
  it("names a resize", () => {
    expect(sum(appt({ ends_at: "2030-01-07T16:30:00Z" }))).toBe("Resized to 1h 30m");
    expect(sum(appt({ ends_at: "2030-01-07T15:45:00Z" }))).toBe("Resized to 45m");
    expect(sum(appt({ ends_at: "2030-01-07T17:00:00Z" }))).toBe("Resized to 2h");
  });
  it("combines a reassign and a reschedule", () => {
    expect(sum(appt({ tech_id: 11, starts_at: "2030-01-08T20:00:00Z", ends_at: "2030-01-08T21:00:00Z" }))).toBe("Moved to Alex, Tue 14:00");
  });
  it("combines a reschedule and a resize", () => {
    expect(sum(appt({ starts_at: "2030-01-08T20:00:00Z", ends_at: "2030-01-08T22:00:00Z" }))).toBe("Rescheduled to Tue 14:00, resized to 2h");
  });
  it("falls back when the tech is unknown", () => {
    expect(sum(appt({ tech_id: 99, tech_name: null }))).toBe("Moved to user 99");
  });
  it("says so when nothing changed", () => expect(sum(appt())).toBe("No change"));
});

describe("isStale / ageMinutes / oldestFetch", () => {
  const now = new Date("2030-01-07T15:00:00Z");
  const ago = (min: number) => new Date(now.getTime() - min * 60_000).toISOString();
  it("treats null as stale", () => expect(isStale(null, now)).toBe(true));
  it("is fresh at 14 minutes", () => expect(isStale(ago(14), now)).toBe(false));
  it("is fresh at exactly 15 minutes", () => expect(isStale(ago(15), now)).toBe(false));
  it("is stale at 16 minutes", () => expect(isStale(ago(16), now)).toBe(true));
  it("counts whole minutes and never goes negative", () => {
    expect(ageMinutes(ago(14), now)).toBe(14);
    expect(ageMinutes(ago(-5), now)).toBe(0);
  });
  it("takes the oldest fetch, and null when any tech was never fetched", () => {
    const r = (f: string | null): AvailabilityRow => ({ user_id: 1, timezone: CHI, working: [], time_off: [], time_off_pending: [], appointments: [], free: [], outlook_busy: [], outlook_fetched_at: f });
    expect(oldestFetch([r(ago(3)), r(ago(9))])).toBe(ago(9));
    expect(oldestFetch([r(ago(3)), r(null)])).toBeNull();
    expect(oldestFetch([])).toBeNull();
  });
});
