import { api } from "../api";

export type PortalAppointment = {
  id: number;
  ticket_id: number;
  ticket_number: number | null;
  ticket_subject: string | null;
  starts_at: string;
  ends_at: string;
  tech_first_name: string | null;
};

export const fetchPortalAppointments = () => api<PortalAppointment[]>("/portal/appointments");

/** Upcoming (not yet ended) soonest first, then past ones, most recent first. */
export function splitAppointments(rows: PortalAppointment[], now: Date = new Date()) {
  const t = now.getTime();
  const upcoming = rows.filter((a) => new Date(a.ends_at).getTime() >= t).sort((a, b) => a.starts_at.localeCompare(b.starts_at));
  const past = rows.filter((a) => new Date(a.ends_at).getTime() < t).sort((a, b) => b.starts_at.localeCompare(a.starts_at));
  return { upcoming, past };
}

export function dateLabel(iso: string) {
  return new Date(iso).toLocaleDateString(undefined, { weekday: "short", year: "numeric", month: "short", day: "numeric" });
}

export function timeRange(startIso: string, endIso: string) {
  const f = (s: string) => new Date(s).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
  return `${f(startIso)} – ${f(endIso)}`;
}
