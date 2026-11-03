import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { AuditEntry, Page, User, api } from "../api";
import { Button, ErrorMsg, Field, fmt, inputCls } from "../ui";

const show = (v: unknown) => (v === null || v === undefined || v === "" ? "(empty)" : typeof v === "object" ? JSON.stringify(v) : String(v));

function Entry({ a }: { a: AuditEntry }) {
  const [raw, setRaw] = useState(false);
  return (
    <li className="space-y-1 p-3 text-sm">
      <div className="font-medium">{a.summary}</div>
      <div className="text-xs text-slate-500">{fmt(a.occurred_at)} · <span className="font-mono">{a.action}</span></div>
      {a.changes.length > 0 && (
        <ul className="space-y-0.5">
          {a.changes.map((c) => <li key={c.field} className="break-words">{c.label}: {show(c.before)} → {show(c.after)}</li>)}
        </ul>
      )}
      <button type="button" aria-expanded={raw} onClick={() => setRaw(!raw)} aria-label={`Raw data for ${a.summary}`} className="min-h-[32px] rounded px-1 text-xs text-blue-700 underline focus-visible:outline focus-visible:outline-2">{raw ? "Hide raw" : "Show raw"}</button>
      {raw && <pre className="overflow-x-auto whitespace-pre-wrap break-words rounded bg-slate-100 p-2 text-xs">{JSON.stringify({ before: a.before, after: a.after, detail: a.detail }, null, 2)}</pre>}
    </li>
  );
}

export default function Audit() {
  const [action, setAction] = useState("");
  const [actorId, setActorId] = useState("");
  const [entityType, setEntityType] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [offset, setOffset] = useState(0);
  const limit = 50;
  const users = useQuery({ queryKey: ["users"], queryFn: () => api<User[]>("/users") });
  const types = useQuery({ queryKey: ["audit-entity-types"], queryFn: () => api<{ value: string; label: string }[]>("/audit/entity-types") });
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  for (const [k, v] of Object.entries({ action, actor_id: actorId, entity_type: entityType, date_from: from, date_to: to })) if (v) params.set(k, v);
  const q = useQuery({ queryKey: ["audit", params.toString()], queryFn: () => api<Page<AuditEntry>>(`/audit?${params}`), placeholderData: keepPreviousData });
  const set = (f: (v: string) => void) => (e: { target: { value: string } }) => { f(e.target.value); setOffset(0); };
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold tracking-tight">Audit log</h1>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <Field label="Person">
          <select className={inputCls} value={actorId} onChange={set(setActorId)}>
            <option value="">Anyone</option>
            {users.data?.map((u) => <option key={u.id} value={u.id}>{u.display_name}</option>)}
          </select>
        </Field>
        <Field label="Record type">
          <select className={inputCls} value={entityType} onChange={set(setEntityType)}>
            <option value="">Any</option>
            {types.data?.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
          </select>
        </Field>
        <Field label="From"><input type="date" max={to || undefined} className={inputCls} value={from} onChange={set(setFrom)} /></Field>
        <Field label="To"><input type="date" min={from || undefined} className={inputCls} value={to} onChange={set(setTo)} /></Field>
        <Field label="Action starts with"><input className={inputCls} value={action} onChange={set(setAction)} /></Field>
      </div>
      <Button variant="secondary" onClick={() => { setAction(""); setActorId(""); setEntityType(""); setFrom(""); setTo(""); setOffset(0); }}>Reset filters</Button>
      <ErrorMsg error={q.error} />
      <ErrorMsg error={types.error} />
      <div className="rounded-xl border border-slate-200 bg-surface shadow-card">
        {q.isLoading && <p className="p-3 text-sm text-slate-500">Loading…</p>}
        {q.data && q.data.items.length === 0 ? (
          <p className="p-3 text-sm text-slate-500">No audit entries match these filters.</p>
        ) : (
          <ul className="divide-y divide-slate-100">{q.data?.items.map((a) => <Entry key={a.id} a={a} />)}</ul>
        )}
      </div>
      <nav aria-label="Audit paging" className="flex items-center gap-3 text-sm">
        <Button variant="secondary" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - limit))}><span aria-hidden="true">← </span>Newer</Button>
        <span aria-live="polite">{q.data && q.data.total > 0 ? `${offset + 1}–${Math.min(offset + limit, q.data.total)} of ${q.data.total}` : ""}</span>
        <Button variant="secondary" disabled={!q.data || offset + limit >= q.data.total} onClick={() => setOffset(offset + limit)}>Older<span aria-hidden="true"> →</span></Button>
      </nav>
    </div>
  );
}
