import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { KbArticleSummary, KbStatus, KbVisibility, Page, api } from "../../api";
import { can, useMe } from "../../auth";
import { Button, Card, ErrorMsg, fmt, inputCls } from "../../ui";

const PAGE_SIZE = 25;

export function VisibilityBadge({ visibility }: { visibility: KbVisibility }) {
  const cls = visibility === "client" ? "bg-green-100 text-green-800" : "bg-slate-100 text-slate-600";
  return <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${cls}`}>{visibility === "client" ? "Client" : "Internal"}</span>;
}

export function StatusBadge({ status }: { status: KbStatus }) {
  const cls = status === "published" ? "bg-blue-100 text-blue-800" : status === "draft" ? "bg-amber-100 text-amber-800" : "bg-slate-100 text-slate-500";
  return <span className={`rounded-full px-2 py-0.5 text-xs font-semibold capitalize ${cls}`}>{status}</span>;
}

export default function KnowledgeBase() {
  const { data: me } = useMe();
  const nav = useNavigate();
  const [text, setText] = useState("");
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [visibility, setVisibility] = useState("");
  const [offset, setOffset] = useState(0);

  // Debounce typing; the API rejects queries shorter than 2 characters, so those are not sent.
  useEffect(() => {
    const t = setTimeout(() => {
      const v = text.trim();
      setQ(v.length >= 2 ? v : "");
      setOffset(0);
    }, 300);
    return () => clearTimeout(t);
  }, [text]);

  const params = new URLSearchParams();
  if (q) params.set("q", q);
  if (status) params.set("status", status);
  if (visibility) params.set("visibility", visibility);
  params.set("limit", String(PAGE_SIZE));
  params.set("offset", String(offset));
  const list = useQuery({
    queryKey: ["kb", "articles", q, status, visibility, offset],
    queryFn: () => api<Page<KbArticleSummary>>(`/kb/articles?${params}`),
  });
  const d = list.data;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-bold">Knowledge base</h1>
        {can(me, "kb:write") && <Button onClick={() => nav("/kb/new")}>New article</Button>}
      </div>
      <Card title="Articles">
        <div className="mb-3 flex flex-wrap gap-2">
          <input type="search" aria-label="Search articles" placeholder="Search articles…" className={`${inputCls} sm:max-w-xs`} value={text} onChange={(e) => setText(e.target.value)} />
          <select aria-label="Status" className={`${inputCls} sm:w-40`} value={status} onChange={(e) => { setStatus(e.target.value); setOffset(0); }}>
            <option value="">Any status</option>
            <option value="draft">Draft</option>
            <option value="published">Published</option>
            <option value="archived">Archived</option>
          </select>
          <select aria-label="Visibility" className={`${inputCls} sm:w-40`} value={visibility} onChange={(e) => { setVisibility(e.target.value); setOffset(0); }}>
            <option value="">Any visibility</option>
            <option value="internal">Internal</option>
            <option value="client">Client</option>
          </select>
        </div>
        {text.trim().length === 1 && <p className="mb-2 text-xs text-slate-500">Type at least 2 characters to search.</p>}
        <ErrorMsg error={list.error} />
        <div className="overflow-x-auto">
          <table className="w-full min-w-[34rem] text-left text-sm">
            <thead className="border-b border-slate-200 text-slate-500"><tr><th className="p-2">Title</th><th>Visibility</th><th>Status</th><th>Tags</th><th>Updated</th></tr></thead>
            <tbody>
              {d?.items.map((a) => (
                <tr key={a.id} className="border-b border-slate-100 last:border-0">
                  <td className="p-2"><Link className="font-medium text-blue-700 hover:underline" to={`/kb/${a.id}`}>{a.title}</Link></td>
                  <td><VisibilityBadge visibility={a.visibility} /></td>
                  <td><StatusBadge status={a.status} /></td>
                  <td className="text-slate-500">{a.tags.join(", ") || "—"}</td>
                  <td className="text-slate-500">{fmt(a.updated_at)}</td>
                </tr>
              ))}
              {d?.items.length === 0 && <tr><td colSpan={5} className="p-2 text-slate-500">No articles found.</td></tr>}
            </tbody>
          </table>
        </div>
        {d && d.total > PAGE_SIZE && (
          <div className="mt-3 flex items-center gap-3 text-sm">
            <Button variant="secondary" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>Previous</Button>
            <span className="text-slate-500">{offset + 1}–{Math.min(offset + PAGE_SIZE, d.total)} of {d.total}</span>
            <Button variant="secondary" disabled={offset + PAGE_SIZE >= d.total} onClick={() => setOffset(offset + PAGE_SIZE)}>Next</Button>
          </div>
        )}
      </Card>
    </div>
  );
}
