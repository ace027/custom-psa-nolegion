import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { HuduArticles, api } from "../api";
import { Card, ErrorMsg } from "../ui";

const muted = "text-sm text-slate-500";

export default function HuduArticlesCard({ ticketId, isAdmin }: { ticketId: number; isAdmin: boolean }) {
  const q = useQuery({ queryKey: ["hudu-articles", ticketId], queryFn: () => api<HuduArticles>(`/tickets/${ticketId}/hudu-articles`) });
  const d = q.data;
  return (
    <Card title="Hudu articles">
      <ErrorMsg error={q.error ?? (d?.error ? `Could not reach Hudu: ${d.error}` : null)} />
      {q.isLoading && <p className={muted}>Loading…</p>}
      {d && !d.configured && (
        <p className={muted}>
          {isAdmin ? <Link className="text-blue-700 hover:underline" to="/integrations">Connect Hudu on the Integrations page</Link> : "Connect Hudu on the Integrations page"} to see related articles
        </p>
      )}
      {d?.configured && !d.error && d.articles.length === 0 && <p className={muted}>No related Hudu articles</p>}
      <ul className="divide-y divide-slate-100 text-sm">
        {d?.articles.slice(0, 5).map((a) => (
          <li key={a.id} className="flex flex-wrap items-center gap-2 py-2">
            <a className="font-medium text-blue-700 hover:underline" href={a.url} target="_blank" rel="noopener noreferrer">{a.title}</a>
            <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${a.scope === "client" ? "bg-blue-100 text-blue-800" : "bg-slate-100 text-slate-600"}`}>
              {a.scope === "client" ? "Client" : "Global"}
            </span>
            {a.updated_at && <span className="text-slate-500">Updated {new Date(a.updated_at).toLocaleDateString()}</span>}
          </li>
        ))}
      </ul>
    </Card>
  );
}
