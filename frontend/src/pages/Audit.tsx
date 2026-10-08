import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { AuditEntry, Page, api } from "../api";
import { ErrorMsg, Field, inputCls } from "../ui";

export default function Audit() {
  const [action, setAction] = useState("");
  const [offset, setOffset] = useState(0);
  const limit = 50;
  const q = useQuery({
    queryKey: ["audit", action, offset],
    queryFn: () => api<Page<AuditEntry>>(`/audit?limit=${limit}&offset=${offset}&action=${encodeURIComponent(action)}`),
  });
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold tracking-tight">Audit log</h1>
      <div className="w-64">
        <Field label="Action prefix (e.g. auth., contact.)">
          <input className={inputCls} value={action} onChange={(e) => { setAction(e.target.value); setOffset(0); }} />
        </Field>
      </div>
      <ErrorMsg error={q.error} />
      <table className="w-full rounded-lg border border-slate-200 bg-surface text-left text-sm">
        <thead className="border-b border-slate-200 text-slate-500">
          <tr><th className="p-2">When</th><th>Actor</th><th>Action</th><th>Entity</th><th>Detail</th></tr>
        </thead>
        <tbody>
          {q.data?.items.map((a) => (
            <tr key={a.id} className="border-b border-slate-100 align-top">
              <td className="p-2 whitespace-nowrap">{new Date(a.occurred_at).toLocaleString()}</td>
              <td>{a.actor_id ? `user ${a.actor_id}` : a.actor_type}</td>
              <td className="font-mono text-xs">{a.action}</td>
              <td>{a.entity_type ? `${a.entity_type} #${a.entity_id}` : ""}</td>
              <td className="max-w-md truncate font-mono text-xs" title={JSON.stringify(a.detail ?? a.after)}>
                {JSON.stringify(a.detail ?? a.after ?? "")}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="flex items-center gap-3 text-sm">
        <button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - limit))} className="disabled:opacity-40">← Newer</button>
        <span>{q.data ? `${offset + 1}–${Math.min(offset + limit, q.data.total)} of ${q.data.total}` : ""}</span>
        <button disabled={!q.data || offset + limit >= q.data.total} onClick={() => setOffset(offset + limit)} className="disabled:opacity-40">Older →</button>
      </div>
    </div>
  );
}
