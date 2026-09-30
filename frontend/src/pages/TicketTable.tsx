import { Link } from "react-router-dom";
import { STATUS_LABEL, Ticket } from "../api";
import { SlaBadge } from "../ui";

export default function TicketTable({ tickets, empty = "No tickets." }: { tickets: Ticket[]; empty?: string }) {
  return (
    <table className="w-full rounded-lg border border-slate-200 bg-white text-left text-sm">
      <thead className="border-b border-slate-200 text-slate-500">
        <tr>
          <th className="p-2">#</th>
          <th>Subject</th>
          <th>Organization</th>
          <th>Priority</th>
          <th>Status</th>
          <th>Assignee</th>
          <th>SLA</th>
        </tr>
      </thead>
      <tbody>
        {tickets.map((t) => (
          <tr key={t.id} className="border-b border-slate-100">
            <td className="p-2 text-slate-500">{t.number}</td>
            <td>
              <Link to={`/tickets/${t.id}`} className="font-medium text-blue-700 hover:underline">
                {t.subject}
              </Link>
            </td>
            <td>{t.needs_triage ? <b className="text-amber-700">Needs triage</b> : t.organization_name}</td>
            <td>{t.priority_name}</td>
            <td>{STATUS_LABEL[t.status]}</td>
            <td>{t.assignee_name ?? <span className="text-slate-400">unassigned</span>}</td>
            <td>
              <SlaBadge state={t.sla_state} />
            </td>
          </tr>
        ))}
        {tickets.length === 0 && (
          <tr>
            <td colSpan={7} className="p-3 text-slate-500">
              {empty}
            </td>
          </tr>
        )}
      </tbody>
    </table>
  );
}
