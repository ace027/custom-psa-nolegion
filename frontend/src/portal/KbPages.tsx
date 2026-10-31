import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError, PortalKbArticle, PortalKbSummary, api } from "../api";
import { Card, ErrorMsg, fmt, inputCls } from "../ui";

export function KbList() {
  const [text, setText] = useState("");
  const [q, setQ] = useState("");
  useEffect(() => {
    const t = setTimeout(() => { const v = text.trim(); setQ(v.length >= 2 ? v : ""); }, 300);
    return () => clearTimeout(t);
  }, [text]);
  const list = useQuery({
    queryKey: ["portal", "kb", q],
    queryFn: () => api<PortalKbSummary[]>(`/portal/kb${q ? `?q=${encodeURIComponent(q)}` : ""}`),
  });
  return (
    <Card title="Help articles">
      <input type="search" aria-label="Search help articles" placeholder="Search help articles…" className={`${inputCls} mb-3 sm:max-w-xs`} value={text} onChange={(e) => setText(e.target.value)} />
      <ErrorMsg error={list.error} />
      <ul className="divide-y divide-slate-100 text-sm">
        {list.data?.map((a) => (
          <li key={a.id} className="py-2">
            <Link className="font-medium text-blue-700 hover:underline" to={`/portal/kb/${a.id}`}>{a.title}</Link>
            <p className="text-slate-500">{a.snippet}</p>
          </li>
        ))}
        {list.data?.length === 0 && <li className="py-2 text-slate-500">No articles found.</li>}
      </ul>
    </Card>
  );
}

export function KbArticlePage() {
  const { id } = useParams();
  const q = useQuery({
    queryKey: ["portal", "kb", "article", id],
    retry: false,
    queryFn: () => api<PortalKbArticle>(`/portal/kb/${id}`),
  });
  const notFound = q.error instanceof ApiError && q.error.status === 404;
  return (
    <div className="space-y-4">
      <Link className="text-sm text-blue-700 hover:underline" to="/portal/kb">← All help articles</Link>
      {notFound ? <p role="status" className="text-sm text-slate-600">This article was not found.</p> : <ErrorMsg error={q.error} />}
      {q.data && (
        <Card title={q.data.title}>
          <p className="mb-2 text-xs text-slate-500">Updated {fmt(q.data.updated_at)}</p>
          <p className="whitespace-pre-wrap text-sm">{q.data.body}</p>
        </Card>
      )}
    </div>
  );
}
