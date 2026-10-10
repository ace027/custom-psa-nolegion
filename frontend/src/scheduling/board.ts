import type { Appointment, AppointmentPatch, AvailabilityRow, Conflict, ConflictKind, StaffUser, Window } from "./api";
import { formatInZone, fromBoardDate, toBoardDate } from "./zone";

export interface BoardEvent {
  id: number;
  title: string;
  start: Date;
  end: Date;
  resourceId: number;
  conflicts: Conflict[];
  appointment: Appointment;
}
export interface BoardResource {
  id: number;
  title: string;
}
export type BlockKind = "off_hours" | "time_off" | "time_off_pending";
export interface BackgroundBlock {
  resourceId: number;
  kind: BlockKind;
  start: Date;
  end: Date;
}

export function toEvents(appointments: Appointment[], zone: string): BoardEvent[] {
  return appointments.map((a) => ({
    id: a.id,
    title: [a.ticket_number != null ? `#${a.ticket_number}` : null, a.organization_name].filter(Boolean).join(" "),
    start: toBoardDate(a.starts_at, zone),
    end: toBoardDate(a.ends_at, zone),
    resourceId: a.tech_id,
    conflicts: a.conflicts,
    appointment: a,
  }));
}

export function toResources(staff: StaffUser[]): BoardResource[] {
  return staff.map((s) => ({ id: s.id, title: s.display_name }));
}

const ms = (iso: string) => new Date(iso).getTime();

/** Parts of [from, to) not covered by `windows`. */
function complement(windows: Window[], from: number, to: number): [number, number][] {
  const out: [number, number][] = [];
  let cursor = from;
  for (const w of [...windows].sort((a, b) => ms(a.starts_at) - ms(b.starts_at))) {
    const s = Math.max(ms(w.starts_at), from);
    const e = Math.min(ms(w.ends_at), to);
    if (e <= s) continue;
    if (s > cursor) out.push([cursor, s]);
    cursor = Math.max(cursor, e);
  }
  if (cursor < to) out.push([cursor, to]);
  return out;
}

/** Shading per tech inside the visible range: off-hours (outside the working windows), approved time off and pending time off. */
export function backgroundBlocks(
  availability: AvailabilityRow[],
  zone: string,
  range: { from: string; to: string },
): BackgroundBlock[] {
  const from = ms(range.from);
  const to = ms(range.to);
  const board = (t: number) => toBoardDate(new Date(t).toISOString(), zone);
  const out: BackgroundBlock[] = [];
  for (const row of availability) {
    const add = (kind: BlockKind, s: number, e: number) => {
      const lo = Math.max(s, from);
      const hi = Math.min(e, to);
      if (hi > lo) out.push({ resourceId: row.user_id, kind, start: board(lo), end: board(hi) });
    };
    for (const [s, e] of complement(row.working, from, to)) add("off_hours", s, e);
    for (const w of row.time_off) add("time_off", ms(w.starts_at), ms(w.ends_at));
    for (const w of row.time_off_pending) add("time_off_pending", ms(w.starts_at), ms(w.ends_at));
  }
  return out;
}

/** The minimal PATCH for a drop or resize: only the changed fields, or null if nothing changed. */
export function dropPatch(
  a: Appointment,
  target: { start: Date; end: Date; resourceId: number },
  zone: string,
): AppointmentPatch | null {
  const patch: AppointmentPatch = {};
  if (target.resourceId !== a.tech_id) patch.tech_id = target.resourceId;
  const start = fromBoardDate(target.start, zone);
  const end = fromBoardDate(target.end, zone);
  if (ms(start) !== ms(a.starts_at)) patch.starts_at = start;
  if (ms(end) !== ms(a.ends_at)) patch.ends_at = end;
  return Object.keys(patch).length ? patch : null;
}

/** The PATCH that puts `before`'s tech and times back (always all three, so a concurrent change is overwritten too). */
export function undoPatch(before: Appointment, _after: Appointment): AppointmentPatch {
  return {
    tech_id: before.tech_id,
    starts_at: new Date(before.starts_at).toISOString(),
    ends_at: new Date(before.ends_at).toISOString(),
  };
}

export const CONFLICT_LABEL: Record<ConflictKind, string> = {
  outside_hours: "Outside working hours",
  time_off: "During approved time off",
  time_off_pending: "During pending time off",
  overlap: "Overlaps another appointment",
};
export const conflictLabel = (kind: ConflictKind): string => CONFLICT_LABEL[kind];

function duration(a: Appointment): string {
  const minutes = Math.round((ms(a.ends_at) - ms(a.starts_at)) / 60000);
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return [h ? `${h}h` : "", m || !h ? `${m}m` : ""].filter(Boolean).join(" ");
}

/** Toast text for what changed, e.g. 'Moved to Sam', 'Rescheduled to Tue 14:00', 'Resized to 1h 30m'. */
export function moveSummary(before: Appointment, after: Appointment, staff: StaffUser[], zone: string): string {
  const techChanged = before.tech_id !== after.tech_id;
  const startChanged = ms(before.starts_at) !== ms(after.starts_at);
  const lengthChanged = ms(before.ends_at) - ms(before.starts_at) !== ms(after.ends_at) - ms(after.starts_at);
  const endOnly = !startChanged && ms(before.ends_at) !== ms(after.ends_at);
  const resized = lengthChanged || endOnly;
  const who = staff.find((s) => s.id === after.tech_id)?.display_name ?? after.tech_name ?? `user ${after.tech_id}`;
  const when = formatInZone(after.starts_at, zone, "EEE HH:mm");
  const size = duration(after);
  if (techChanged) {
    return ["Moved to " + who, startChanged ? when : "", resized ? `resized to ${size}` : ""].filter(Boolean).join(", ");
  }
  if (startChanged) return resized ? `Rescheduled to ${when}, resized to ${size}` : `Rescheduled to ${when}`;
  if (resized) return `Resized to ${size}`;
  return "No change";
}
