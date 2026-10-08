import { Link } from "react-router-dom";
import { STATUS_LABEL, Ticket } from "../api";
import { SlaBadge } from "../ui";

export interface SortState {
  key: string;
  desc: boolean;
}

interface Props {
  tickets: Ticket[];
  empty?: string;
  /** Sorting and selection are opt-in; the dashboard uses the plain table. */
  sort?: SortState;
  onSort?: (key: string) => void;
  selected?: Set<number>;
  onToggle?: (id: number) => void;
  onToggleAll?: (on: boolean) => void;
}

export default function TicketTable({ tickets, empty = "No tickets.", sort, onSort, selected, onToggle, onToggleAll }: Props) {
  const selectable = !!selected && !!onToggle;
  const allOn = selectable && tickets.length > 0 && tickets.every((t) => selected.has(t.id));
  const head = (label: string, key?: string) =>
    key && onSort ? (
      <th aria-sort={sort?.key === key ? (sort.desc ? "descending" : "ascending") : undefined}>
        <button type="button" className="font-semibold hover:underline" onClick={() => onSort(key)}>
          {label}
          {sort?.key === key ? (sort.desc ? " ▼" : " ▲") : ""}
        </button>
      </th>
    ) : (
      <th>{label}</th>
    );
  return (
    <table className="w-full rounded-lg border border-slate-200 bg-surface text-left text-sm">
      <thead className="border-b border-slate-200 text-slate-500">
        <tr>
          {selectable && (
            <th className="w-8 p-2">
              <input type="checkbox" aria-label="Select all tickets" checked={allOn} onChange={(e) => onToggleAll?.(e.target.checked)} />
            </th>
          )}
          <th className="p-2">{onSort ? <button type="button" className="font-semibold hover:underline" onClick={() => onSort("number")}>#{sort?.key === "number" ? (sort.desc ? " ▼" : " ▲") : ""}</button> : "#"}</th>
          <th>Subject</th>
          <th>Organization</th>
          {head("Priority", "priority")}
          <th>Status</th>
          <th>Assignee</th>
          {head("SLA due", "due")}
        </tr>
      </thead>
      <tbody>
        {tickets.map((t) => (
          <tr key={t.id} className="border-b border-slate-100">
            {selectable && (
              <td className="p-2">
                <input type="checkbox" aria-label={`Select ticket ${t.number}`} checked={selected.has(t.id)} onChange={() => onToggle(t.id)} />
              </td>
            )}
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
            <td colSpan={selectable ? 8 : 7} className="p-3 text-slate-500">
              {empty}
            </td>
          </tr>
        )}
      </tbody>
    </table>
  );
}
