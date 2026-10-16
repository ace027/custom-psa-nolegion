import { api } from "../api";

// Mirrors backend/app/oncall_schemas.py. Times are ISO 8601 strings.
export interface Member {
  user_id: number;
  name: string;
  position: number;
}
export interface Rotation {
  id: number;
  name: string;
  handoff_weekday: number; // 0 = Monday
  handoff_time: string; // HH:MM:SS
  anchor_date: string; // yyyy-MM-dd, on the handoff weekday
  active: boolean;
  members: Member[];
}
export interface RotationCreate {
  name: string;
  handoff_weekday: number;
  handoff_time: string;
  anchor_date: string;
  member_ids: number[];
}
export interface RotationPatch {
  name?: string;
  handoff_weekday?: number;
  handoff_time?: string;
  anchor_date?: string;
  active?: boolean;
  member_ids?: number[];
}
export interface Override {
  id: number;
  rotation_id: number;
  user_id: number;
  user_name: string | null;
  starts_at: string;
  ends_at: string;
  reason: string | null;
  created_at: string;
}
export interface OverrideCreate {
  user_id: number;
  starts_at: string;
  ends_at: string;
  reason?: string | null;
}
export interface OnCallNow {
  rotation_id: number;
  rotation_name: string;
  user_id: number | null;
  user_name: string | null;
  until: string | null;
  source: "rotation" | "override" | null;
}
export interface Shift {
  rotation_id: number;
  user_id: number;
  user_name: string | null;
  starts_at: string;
  ends_at: string;
  source: "rotation" | "override";
}

export const oncallKeys = {
  all: ["oncall"] as const,
  rotations: () => ["oncall", "rotations"] as const,
  overrides: (rotationId: number) => ["oncall", "overrides", rotationId] as const,
  now: () => ["oncall", "now"] as const,
  schedule: (from: string, to: string) => ["oncall", "schedule", from, to] as const,
};

export const listRotations = (): Promise<Rotation[]> => api<Rotation[]>("/oncall/rotations");
export const createRotation = (body: RotationCreate): Promise<Rotation> =>
  api<Rotation>("/oncall/rotations", { method: "POST", json: body });
export const updateRotation = (id: number, patch: RotationPatch): Promise<Rotation> =>
  api<Rotation>(`/oncall/rotations/${id}`, { method: "PATCH", json: patch });
export const listOverrides = (rotationId: number): Promise<Override[]> =>
  api<Override[]>(`/oncall/rotations/${rotationId}/overrides`);
export const createOverride = (rotationId: number, body: OverrideCreate): Promise<Override> =>
  api<Override>(`/oncall/rotations/${rotationId}/overrides`, { method: "POST", json: body });
export const deleteOverride = (id: number): Promise<unknown> => api(`/oncall/overrides/${id}`, { method: "DELETE" });
export const getOnCallNow = (): Promise<OnCallNow[]> => api<OnCallNow[]>("/oncall/now");
export const getOnCallSchedule = (from: string, to: string): Promise<Shift[]> =>
  api<Shift[]>(`/oncall/schedule?${new URLSearchParams({ start: from, end: to })}`);

export const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

/** Weekday (0 = Monday) of a yyyy-MM-dd date, or null when malformed. */
export function weekdayOf(day: string): number | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(day);
  if (!m) return null;
  return (new Date(Date.UTC(+m[1], +m[2] - 1, +m[3])).getUTCDay() + 6) % 7;
}

/** The first date on or after `day` that falls on `weekday`. */
export function nextWeekday(day: string, weekday: number): string {
  const cur = weekdayOf(day);
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(day);
  if (cur === null || !m) return day;
  const add = (weekday - cur + 7) % 7;
  return new Date(Date.UTC(+m[1], +m[2] - 1, +m[3] + add)).toISOString().slice(0, 10);
}

/** Move the member at `index` by `delta` (-1 up, +1 down); a move off either end returns the list unchanged. */
export function moveMember<T>(items: T[], index: number, delta: -1 | 1): T[] {
  const to = index + delta;
  if (to < 0 || to >= items.length) return items;
  const out = [...items];
  [out[index], out[to]] = [out[to], out[index]];
  return out;
}
