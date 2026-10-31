import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { KbArticle, KbArticleInput, KbStatus, KbVisibility, api } from "../../api";
import { can, useMe } from "../../auth";
import { Button, Card, ErrorMsg, Field, fmt, inputCls } from "../../ui";
import { StatusBadge, VisibilityBadge } from "./KnowledgeBase";

export default function ArticlePage() {
  const { id } = useParams();
  const isNew = id === undefined;
  const { data: me } = useMe();
  const canWrite = can(me, "kb:write");
  const q = useQuery({ queryKey: ["kb", "article", id], enabled: !isNew, queryFn: () => api<KbArticle>(`/kb/articles/${id}`) });
  return (
    <div className="space-y-4">
      <Link className="text-sm text-blue-700 hover:underline" to="/kb">← Knowledge base</Link>
      {isNew ? (
        canWrite ? <Editor key="new" article={null} /> : <p className="text-sm text-slate-600">You do not have permission to write articles.</p>
      ) : (
        <>
          <ErrorMsg error={q.error} />
          {q.isLoading && <p className="text-sm text-slate-500">Loading…</p>}
          {q.data && <Article key={`${q.data.id}-${q.data.updated_at}`} article={q.data} canWrite={canWrite} />}
        </>
      )}
    </div>
  );
}

function Article({ article, canWrite }: { article: KbArticle; canWrite: boolean }) {
  const [editing, setEditing] = useState(false);
  const qc = useQueryClient();
  const archive = useMutation({
    mutationFn: () => api<KbArticle>(`/kb/articles/${article.id}`, { method: "PATCH", json: { status: "archived" } }),
    onSuccess: (a) => { qc.setQueryData(["kb", "article", String(a.id)], a); qc.invalidateQueries({ queryKey: ["kb"] }); },
  });
  if (editing) return <Editor article={article} onDone={() => setEditing(false)} />;
  return (
    <Card
      title={article.title}
      actions={canWrite && (
        <div className="flex gap-2">
          <Button variant="secondary" onClick={() => setEditing(true)}>Edit</Button>
          {article.status !== "archived" && <Button variant="danger" disabled={archive.isPending} onClick={() => { if (window.confirm("Archive this article? It will no longer be suggested or shown in the portal.")) archive.mutate(); }}>Archive</Button>}
        </div>
      )}
    >
      <div className="mb-3 flex flex-wrap items-center gap-2 text-xs text-slate-500">
        <VisibilityBadge visibility={article.visibility} />
        <StatusBadge status={article.status} />
        {article.tags.length > 0 && <span>Tags: {article.tags.join(", ")}</span>}
        <span>Updated {fmt(article.updated_at)}{article.updated_by_name ? ` by ${article.updated_by_name}` : ""}</span>
      </div>
      <ErrorMsg error={archive.error} />
      <p className="whitespace-pre-wrap text-sm">{article.body}</p>
    </Card>
  );
}

function Editor({ article, onDone }: { article: KbArticle | null; onDone?: () => void }) {
  const nav = useNavigate();
  const qc = useQueryClient();
  const [f, setF] = useState({
    title: article?.title ?? "",
    body: article?.body ?? "",
    visibility: (article?.visibility ?? "internal") as KbVisibility,
    status: (article?.status ?? "draft") as KbStatus,
    tags: article?.tags.join(", ") ?? "",
  });
  const save = useMutation({
    mutationFn: () => {
      const json: KbArticleInput = {
        title: f.title, body: f.body, visibility: f.visibility, status: f.status,
        tags: f.tags.split(",").map((t) => t.trim()).filter(Boolean),
      };
      return article
        ? api<KbArticle>(`/kb/articles/${article.id}`, { method: "PATCH", json })
        : api<KbArticle>("/kb/articles", { method: "POST", json });
    },
    onSuccess: (a) => {
      qc.setQueryData(["kb", "article", String(a.id)], a);
      qc.invalidateQueries({ queryKey: ["kb"] });
      if (article) onDone?.();
      else nav(`/kb/${a.id}`);
    },
  });
  return (
    <Card title={article ? "Edit article" : "New article"}>
      <form className="space-y-3" onSubmit={(e: FormEvent) => { e.preventDefault(); save.mutate(); }}>
        <Field label="Title"><input className={inputCls} required maxLength={200} value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /></Field>
        <Field label="Body"><textarea className={inputCls} required rows={12} maxLength={50000} value={f.body} onChange={(e) => setF({ ...f, body: e.target.value })} /></Field>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Visibility">
            <select className={inputCls} value={f.visibility} onChange={(e) => setF({ ...f, visibility: e.target.value as KbVisibility })}>
              <option value="internal">Internal (staff only)</option>
              <option value="client">Client (shown in the portal when published)</option>
            </select>
          </Field>
          <Field label="Status">
            <select className={inputCls} value={f.status} onChange={(e) => setF({ ...f, status: e.target.value as KbStatus })}>
              <option value="draft">Draft</option>
              <option value="published">Published</option>
              <option value="archived">Archived</option>
            </select>
          </Field>
        </div>
        <Field label="Tags (comma separated)"><input className={inputCls} value={f.tags} onChange={(e) => setF({ ...f, tags: e.target.value })} /></Field>
        <div className="flex gap-2">
          <Button type="submit" disabled={save.isPending}>Save</Button>
          {article && <Button type="button" variant="secondary" onClick={onDone}>Cancel</Button>}
        </div>
        <ErrorMsg error={save.error} />
      </form>
    </Card>
  );
}
