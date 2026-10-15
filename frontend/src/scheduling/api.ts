import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, ApiError, type AppSettings, type User } from "../api";

// Mirrors backend/app/scheduling_schemas.py. Times are ISO 8601 UTC strings.
export type ConflictKind = "outside_hours" | "time_off" | "time_off_pending" | "overlap";
export interface Conflict {
  kind: ConflictKind;
  time_off_id: number | null;
  appointment_id: number | null;
}
export type AppointmentStatus = "scheduled" | "cancelled";
export type SyncState = "pending" | "synced" | "failed" | "skipped" | "off";
export interface AppointmentSync {
  state: SyncState;
  last_error: string | null;
}
export interface Appointment {
  id: number;
  organization_id: number;
  organization_name: string | null;
  ticket_id: number;
  ticket_number: number | null;
  ticket_subject: string | null;
  tech_id: number;
  tech_name: string | null;
  starts_at: string;
  ends_at: string;
  status: AppointmentStatus;
  notes: string | null;
  client_visible: boolean;
  created_by: number | null;
  cancelled_at: string | null;
  cancel_reason: string | null;
  conflicts: Conflict[];
  sync: AppointmentSync;
}
export interface AppointmentCreate {
  ticket_id: number;
  tech_id: number;
  starts_at: string;
  ends_at: string;
  notes?: string | null;
  client_visible?: boolean;
}
export interface AppointmentPatch {
  tech_id?: number;
  starts_at?: string;
  ends_at?: string;
  notes?: string | null;
  client_visible?: boolean;
}
export interface Window {
  starts_at: string;
  ends_at: string;
}
export interface AvailabilityRow {
  user_id: number;
  timezone: string;
  working: Window[];
  time_off: Window[]; // approved only
  time_off_pending: Window[];
  appointments: (Window & { id: number })[];
  free: Window[];
  outlook_busy: (Window & { status: string })[]; // cached Outlook busy time; informational
  outlook_fetched_at: string | null; // null: never fetched
}
export interface SyncFailure {
  appointment_id: number;
  ticket_id: number;
  tech_id: number;
  last_error: string | null;
  updated_at: string;
}
export interface CalendarSyncStatus {
  enabled: boolean;
  pending: number;
  failed: number;
  failures: SyncFailure[];
  busy_fetched_at: string | null;
  busy_errors: number;
}
export interface WorkHoursDay {
  weekday: number; // 0 = Monday
  start_minute: number;
  end_minute: number;
}
export interface Schedule {
  user_id: number;
  timezone: string;
  timezone_override: string | null;
  uses_default_hours: boolean;
  work_hours: WorkHoursDay[];
}
export type StaffUser = Pick<User, "id" | "display_name" | "role">;

export interface AppointmentListParams {
  from: string;
  to: string;
  techId?: number;
  ticketId?: number;
  withConflicts?: boolean;
}
export interface AvailabilityParams {
  from: string;
  to: string;
  userIds?: number[];
}

export const schedulingKeys = {
  all: ["scheduling"] as const,
  appointments: (params: AppointmentListParams) => ["scheduling", "appointments", params] as const,
  appointment: (id: number) => ["scheduling", "appointment", id] as const,
  availability: (params: AvailabilityParams) => ["scheduling", "availability", params] as const,
  schedule: (userId: number) => ["scheduling", "schedule", userId] as const,
  staff: () => ["scheduling", "staff"] as const,
  orgTimezone: () => ["scheduling", "orgTimezone"] as const,
  syncStatus: () => ["scheduling", "syncStatus"] as const,
};

function query(params: Record<string, string | number | boolean | undefined>): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined) q.set(k, String(v));
  const s = q.toString();
  return s ? `?${s}` : "";
}

export function listAppointments(p: AppointmentListParams): Promise<Appointment[]> {
  return api<Appointment[]>(
    `/appointments${query({
      from: p.from,
      to: p.to,
      tech_id: p.techId,
      ticket_id: p.ticketId,
      with_conflicts: p.withConflicts ? true : undefined,
    })}`,
  );
}
export const getAppointment = (id: number): Promise<Appointment> => api<Appointment>(`/appointments/${id}`);
export const createAppointment = (body: AppointmentCreate): Promise<Appointment> =>
  api<Appointment>("/appointments", { method: "POST", json: body });
export const updateAppointment = (id: number, patch: AppointmentPatch): Promise<Appointment> =>
  api<Appointment>(`/appointments/${id}`, { method: "PATCH", json: patch });
export const cancelAppointment = (id: number, reason?: string): Promise<Appointment> =>
  api<Appointment>(`/appointments/${id}/cancel`, { method: "POST", json: { reason: reason ?? null } });
export function getAvailability(p: AvailabilityParams): Promise<AvailabilityRow[]> {
  return api<AvailabilityRow[]>(
    `/availability${query({ from: p.from, to: p.to, user_ids: p.userIds?.length ? p.userIds.join(",") : undefined })}`,
  );
}
export const getCalendarSyncStatus = (): Promise<CalendarSyncStatus> => api<CalendarSyncStatus>("/calendar-sync/status");
export const retryAppointmentSync = (id: number): Promise<Appointment> =>
  api<Appointment>(`/appointments/${id}/sync/retry`, { method: "POST" });
export const getSchedule = (userId: number): Promise<Schedule> => api<Schedule>(`/users/${userId}/schedule`);

/** Active admins and techs, by display name: the people who can be booked. */
export async function listStaff(): Promise<StaffUser[]> {
  const users = await api<User[]>("/users");
  return users
    .filter((u) => u.is_active && (u.role === "admin" || u.role === "tech"))
    .map(({ id, display_name, role }) => ({ id, display_name, role }))
    .sort((a, b) => a.display_name.localeCompare(b.display_name));
}
export async function getOrgTimezone(): Promise<string> {
  return (await api<AppSettings>("/settings")).timezone;
}

/** Why a retry failed, in words for the person who clicked: 409 means someone already retried it. */
export const retryErrorText = (e: unknown): string =>
  e instanceof ApiError && e.status === 409
    ? "This sync was already retried; it is no longer failed."
    : e instanceof Error
      ? e.message
      : "Retry failed";

/** Retry a failed Outlook push, then refresh every scheduling query (board, appointment, status). */
export function useRetrySync(handlers: { onSuccess?(a: Appointment): void; onError?(e: unknown): void } = {}) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => retryAppointmentSync(id),
    onSuccess: (a) => handlers.onSuccess?.(a),
    onError: (e) => handlers.onError?.(e),
    onSettled: () => qc.invalidateQueries({ queryKey: schedulingKeys.all }),
  });
}
