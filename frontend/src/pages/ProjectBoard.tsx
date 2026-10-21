import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Project, ProjectTask, TicketStatus, TicketStatusRow, api } from "../api";
import { ErrorMsg, inputCls } from "../ui";

// Columns follow the ticket status behavior, so custom status names still land in the right column.
const COLUMNS: { key: string; label: string; behaviors: TicketStatus[]; target: TicketStatus }[] = [
  { key: "new", label: "New", behaviors: ["new"], target: "new" },
  { key: "open", label: "Open", behaviors: ["open"], target: "open" },
  { key: "waiting", label: "Waiting", behaviors: ["waiting_on_customer"], target: "waiting_on_customer" },
  { key: "resolved", label: "Resolved", behaviors: ["resolved", "closed"], target: "resolved" },
];

export default function ProjectBoard({ project, canWrite }: { project: Project; canWrite: boolean }) {
  const qc = useQueryClient();
  const statuses = useQuery({
    queryKey: ["lookup", "ticket-statuses"],
    staleTime: 60_000,
    queryFn: () => api<TicketStatusRow[]>("/ticket-statuses"),
  });
  const move = useMutation({
    mutationFn: ({ task, target }: { task: ProjectTask; target: TicketStatus }) => {
      const row = (Array.isArray(statuses.data) ? statuses.data : [])
        .filter((s) => s.behavior === target && !s.archived_at)
        .sort((a, b) => a.position - b.position)[0];
      if (!row) throw new Error("No ticket status is set up for that column");
      return api(`/tickets/${task.ticket_id}`, { method: "PATCH", json: { status_id: row.id } });
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["project", project.id] }),
  });
  const writable = canWrite && project.status !== "completed" && project.status !== "cancelled";
  return (
    <div className="space-y-3">
      <ErrorMsg error={move.error} />
      {project.tasks.length === 0 && <p className="text-sm text-slate-500">No tasks yet. Add one on the Tasks tab.</p>}
      <div className="grid gap-3 md:grid-cols-4">
        {COLUMNS.map((col) => {
          const tasks = project.tasks.filter((t) => col.behaviors.includes(t.status));
          return (
            <section key={col.key} aria-label={col.label} className="rounded-xl bg-slate-50 p-2">
              <h3 className="mb-2 px-1 text-sm font-semibold text-slate-700">{col.label} ({tasks.length})</h3>
              <ul className="space-y-2">
                {tasks.map((t) => (
                  <li key={t.id} className="rounded-lg border border-slate-200 bg-surface p-2 text-sm shadow-card">
                    <Link className="font-medium text-blue-700 hover:underline" to={`/tickets/${t.ticket_id}`}>#{t.ticket_number}</Link> {t.title}
                    <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-600">
                      <span>{t.assignee_name ?? "Unassigned"}</span>
                      {t.due_date && <span>Due {t.due_date}</span>}
                      {t.blocked && <span className="rounded-full bg-amber-100 px-2 py-0.5 font-semibold text-amber-800">Blocked</span>}
                    </div>
                    {writable && (
                      <select
                        aria-label={`Move #${t.ticket_number}`}
                        className={`${inputCls} mt-2`}
                        value={col.target}
                        disabled={move.isPending}
                        onChange={(e) => move.mutate({ task: t, target: e.target.value as TicketStatus })}
                      >
                        {COLUMNS.map((c) => <option key={c.key} value={c.target}>{c.label}</option>)}
                      </select>
                    )}
                  </li>
                ))}
              </ul>
            </section>
          );
        })}
      </div>
    </div>
  );
}

