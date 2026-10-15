import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Card, ErrorMsg } from "../ui";
import { PortalAppointment, dateLabel, fetchPortalAppointments, splitAppointments, timeRange } from "./appointments";

function Group({ title, rows }: { title: string; rows: PortalAppointment[] }) {
  return (
    <Card title={title}>
      <ul className="divide-y divide-slate-100 text-sm">
        {rows.map((a) => (
          <li key={a.id} className="flex flex-wrap items-center justify-between gap-x-4 py-2">
            <div>
              <div className="font-medium">{dateLabel(a.starts_at)}</div>
              <div className="text-slate-500">{timeRange(a.starts_at, a.ends_at)}{a.tech_first_name ? ` · ${a.tech_first_name}` : ""}</div>
            </div>
            <Link className="text-blue-700 hover:underline" to={`/portal/tickets/${a.ticket_id}`}>
              {a.ticket_number != null ? `#${a.ticket_number} ` : ""}{a.ticket_subject ?? "Ticket"}
            </Link>
          </li>
        ))}
      </ul>
    </Card>
  );
}

export default function AppointmentsPage() {
  const q = useQuery({ queryKey: ["portal", "appointments"], queryFn: fetchPortalAppointments });
  const { upcoming, past } = splitAppointments(q.data ?? []);
  return (
    <div className="space-y-4">
      <ErrorMsg error={q.error} />
      {q.isLoading && <p>Loading…</p>}
      {q.data && q.data.length === 0 && <Card title="Appointments"><p className="text-sm text-slate-500">No appointments scheduled</p></Card>}
      {upcoming.length > 0 && <Group title="Upcoming" rows={upcoming} />}
      {past.length > 0 && <Group title="Past 30 days" rows={past} />}
    </div>
  );
}
