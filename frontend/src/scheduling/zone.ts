import { TZDate } from "@date-fns/tz";
import { format } from "date-fns";

/*
 * The calendar library only knows the browser's local zone. The board shows the organisation's
 * zone, so instants are mapped to a "fake local" Date whose local wall-clock fields equal the
 * wall clock in the board zone, and back. Caveat: a wall clock that repeats (the hour a clock
 * falls back) maps back to its first occurrence.
 */
function wall(z: Date): Date {
  return new Date(z.getFullYear(), z.getMonth(), z.getDate(), z.getHours(), z.getMinutes(), z.getSeconds(), z.getMilliseconds());
}

export function toBoardDate(isoUtc: string, zone: string): Date {
  return wall(new TZDate(new Date(isoUtc).getTime(), zone));
}

export function fromBoardDate(d: Date, zone: string): string {
  const z = new TZDate(d.getFullYear(), d.getMonth(), d.getDate(), d.getHours(), d.getMinutes(), d.getSeconds(), d.getMilliseconds(), zone);
  return new Date(z.getTime()).toISOString();
}

function parseDay(day: string): [number, number, number] {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(day);
  if (!m) throw new Error(`Expected YYYY-MM-DD, got ${day}`);
  return [Number(m[1]), Number(m[2]) - 1, Number(m[3])];
}

function localMidnight(y: number, m: number, d: number, zone: string): string {
  return new Date(new TZDate(y, m, d, zone).getTime()).toISOString();
}

/** UTC instants of local midnight to the next local midnight (23, 24 or 25 hours long). */
export function zoneDayRange(day: string, zone: string): { from: string; to: string } {
  const [y, m, d] = parseDay(day);
  return { from: localMidnight(y, m, d, zone), to: localMidnight(y, m, d + 1, zone) };
}

/** Monday 00:00 to the next Monday 00:00 in the zone, for the week holding `anyDay`. */
export function zoneWeekRange(anyDay: string, zone: string): { from: string; to: string } {
  const [y, m, d] = parseDay(anyDay);
  const sinceMonday = (new Date(Date.UTC(y, m, d)).getUTCDay() + 6) % 7;
  return { from: localMidnight(y, m, d - sinceMonday, zone), to: localMidnight(y, m, d - sinceMonday + 7, zone) };
}

export function formatInZone(isoUtc: string, zone: string, fmt = "HH:mm"): string {
  return format(new TZDate(new Date(isoUtc).getTime(), zone), fmt);
}
