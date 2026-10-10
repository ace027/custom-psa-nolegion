import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { Ticket, api } from "../api";
import { can, useMe } from "../auth";
import { useLookups } from "../lookups";
import {
  getAppointment,
  getOrgTimezone,
  listAppointments,
  schedulingKeys,
  type Appointment,
  type AppointmentListParams,
} from "../scheduling/api";
import { BookingDialog } from "../scheduling/BookingDialog";
import { formatInZone } from "../scheduling/zone";
import { Button, Card, ErrorMsg, Field, inputCls } from "../ui";

const MAX_CONFLICT_LOOKUPS = 10;

/** Date and time in the browser's zone, with a short zone suffix. */
function localWhen(a: Appointment): string {
  const day = new Intl.DateTimeFormat(undefined, { weekday: "short", year: "numeric", month: "short", day: "numeric" });
  const time = new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit", hour12: false });
  const zone = new Intl.DateTimeFormat(undefined, { timeZoneName: "short" }).formatToParts(new Date(a.starts_at)).find((p) => p.type === "timeZoneName")?.value ?? "";
  const [s, e] = [new Date(a.starts_at), new Date(a.ends_at)];
  return `${day.format(s)} ${time.format(s)}–${time.format(e)} ${zone}`.trim();
}

/** Appointments booked on a ticket, with Book and Start timer. */
export default function TicketAppointmentsCard({ ticket: t }: { ticket: Ticket }) {
  const { data: me } = useMe();
  const canWrite = can(me, "schedule:write");
  const lk = useLookups();
  const qc = useQueryClient();
  const [booking, setBooking] = useState(false);
  const [timerFor, setTimerFor] = useState<number | null>(null);
  const [workType, setWorkType] = useState("");

  // from/to are optional on the API when ticket_id is given; cancelled rows are excluded by default.
  const params = { ticketId: t.id } as AppointmentListParams;
  const list = useQuery({ queryKey: schedulingKeys.appointments(params), queryFn: () => listAppointments(params) });
  const zone = useQuery({ queryKey: schedulingKeys.orgTimezone(), queryFn: getOrgTimezone });

  const rows = [...(Array.isArray(list.data) ? list.data : [])]
    .filter((a) => a.status !== "cancelled")
    .sort((a, b) => Date.parse(a.starts_at) - Date.parse(b.starts_at));
  const now = Date.now();
  const upcoming = (a: Appointment) => Date.parse(a.ends_at) > now;

  // The list does not carry conflicts; fetch them one by one for upcoming rows only.
  const lookups = rows.filter(upcoming).slice(0, MAX_CONFLICT_LOOKUPS);
  const details = useQueries({
    queries: lookups.map((a) => ({ queryKey: schedulingKeys.appointment(a.id), queryFn: () => getAppointment(a.id) })),
  });
  const conflicted = new Set(lookups.filter((_, i) => (details[i]?.data?.conflicts.length ?? 0) > 0).map((a) => a.id));

  const start = useMutation({
    mutationFn: (a: Appointment) =>
      api("/timer/start", {
        method: "POST",
        json: {
          ticket_id: t.id,
          work_type_id: Number(workType),
          billable: true,
          note: `Appointment ${zone.data ? formatInZone(a.starts_at, zone.data, "yyyy-MM-dd") : a.starts_at.slice(0, 10)}`,
        },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["timer"] });
      setTimerFor(null);
    },
  });

  const canBook = canWrite && t.status !== "closed" && t.organization_id != null;
  const boardLink = (a: Appointment) =>
    `/dispatch?view=day&date=${formatInZone(a.starts_at, zone.data ?? Intl.DateTimeFormat().resolvedOptions().timeZone, "yyyy-MM-dd")}`;

  return (
    <Card title="Appointments" actions={canBook && zone.data ? <Button onClick={() => setBooking(true)}>Book</Button> : undefined}>
      <ul className="divide-y divide-slate-100 text-sm">
        {rows.map((a) => (
          <li key={a.id} className="py-2">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
              <span>{localWhen(a)}</span>
              <span className="text-slate-600">{a.tech_name ?? `Tech ${a.tech_id}`}</span>
              {conflicted.has(a.id) && <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-800">Has conflicts</span>}
              <Link className="text-blue-700 hover:underline" to={boardLink(a)}>Open on board</Link>
              {canWrite && upcoming(a) && timerFor !== a.id && (
                <Button variant="secondary" onClick={() => { start.reset(); setTimerFor(a.id); }}>Start timer</Button>
              )}
            </div>
            {canWrite && timerFor === a.id && (
              <form className="mt-2 flex flex-wrap items-end gap-2" onSubmit={(e) => { e.preventDefault(); start.mutate(a); }}>
                <Field label="Work type">
                  <select className={inputCls} required value={workType} onChange={(e) => setWorkType(e.target.value)}>
                    <option value="">Select…</option>
                    {lk.workTypes.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
                  </select>
                </Field>
                <Button type="submit" disabled={!workType || start.isPending}>Start</Button>
                <Button type="button" variant="secondary" onClick={() => setTimerFor(null)}>Cancel</Button>
              </form>
            )}
          </li>
        ))}
        {rows.length === 0 && !list.isLoading && <li className="py-1 text-slate-500">No appointments.</li>}
      </ul>
      <ErrorMsg error={list.error ?? start.error} />
      {zone.data && (
        <BookingDialog open={booking} onClose={() => setBooking(false)} initial={{ ticketId: t.id }} zone={zone.data} />
      )}
    </Card>
  );
}
