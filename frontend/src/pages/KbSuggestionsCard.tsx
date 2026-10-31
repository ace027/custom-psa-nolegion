import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { KbArticleSummary, api } from "../api";
import { Card, ErrorMsg } from "../ui";
import { VisibilityBadge } from "./kb/KnowledgeBase";

export default function KbSuggestionsCard({ ticketId }: { ticketId: number }) {
  const q = useQuery({ queryKey: ["kb", "suggestions", ticketId], queryFn: () => api<KbArticleSummary[]>(`/kb/suggestions?ticket_id=${ticketId}`) });
  return (
    <Card title="Suggested articles">
      <ErrorMsg error={q.error} />
      {q.isLoading && <p className="text-sm text-slate-500">Loading…</p>}
      {q.data?.length === 0 && <p className="text-sm text-slate-500">No matching articles</p>}
      <ul className="divide-y divide-slate-100 text-sm">
        {q.data?.slice(0, 5).map((a) => (
          <li key={a.id} className="py-2">
            <div className="flex items-center gap-2">
              <Link className="font-medium text-blue-700 hover:underline" to={`/kb/${a.id}`}>{a.title}</Link>
              <VisibilityBadge visibility={a.visibility} />
            </div>
            <p className="text-slate-500">{a.snippet}</p>
          </li>
        ))}
      </ul>
    </Card>
  );
}
