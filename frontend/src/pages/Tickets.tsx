import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { BulkResult, Organization, Page, STATUSES, STATUS_LABEL, Ticket, api } from "../api";
import { can, useMe } from "../auth";
import { useLookups } from "../lookups";
import { Button, ErrorMsg, Field, inputCls } from "../ui";
import TicketTable, { SortState } from "./TicketTable";

const PAGE = 50;

export default function Tickets() {
  const { data: me } = useMe();
  const nav = useNavigate();
  const qc = useQueryClient();
  const lk = useLookups();
  const [f, setF] = useState({ q: "", status: "", queue_id: "", assignee: "", open_only: true, triage: false });
  const [sort, setSort] = useState<SortState>({ key: "updated", desc: true });
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const params = new URLSearchParams({ limit: String(PAGE), offset: String(offset), sort: sort.key, descending: String(sort.desc) });
  if (f.q) params.set("q", f.q);
  if (f.status) params.set("status", f.status);
  if (f.queue_id) params.set("queue_id", f.queue_id);
  if (f.assignee === "me" && me) params.set("assignee_id", String(me.id));
  if (f.assignee === "none") params.set("unassigned", "true");
  if (f.open_only && !f.status) params.set("open_only", "true");
  if (f.triage) params.set("needs_triage", "true");
  const list = useQuery({ queryKey: ["tickets", params.toString()], queryFn: () => api<Page<Ticket>>(`/tickets?${params}`) });

  const orgs = useQuery({
    queryKey: ["orgs", "", false],
    queryFn: () => api<Page<Organization>>("/organizations?limit=200&include_archived=false&q="),
  });
  const [nt, setNt] = useState({ organization_id: "", subject: "", description: "" });
  const create = useMutation({
    mutationFn: () =>
      api<Ticket>("/tickets", {
        method: "POST",
        json: { organization_id: Number(nt.organization_id), subject: nt.subject, description: nt.description || null },
      }),
    onSuccess: (t) => {
      qc.invalidateQueries({ queryKey: ["tickets"] });
      nav(`/tickets/${t.id}`);
    },
  });
  const set = (k: string, v: string | boolean) => {
    setF({ ...f, [k]: v });
    setOffset(0);
    setSelected(new Set());
  };
  const onSort = (key: string) => {
    setSort(sort.key === key ? { key, desc: !sort.desc } : { key, desc: key === "updated" || key === "created" || key === "number" });
    setOffset(0);
  };
  const toggle = (id: number) => {
    const n = new Set(selected);
    if (!n.delete(id)) n.add(id);
    setSelected(n);
  };
  const items = list.data?.items ?? [];
  const total = list.data?.total ?? 0;
  const canWrite = can(me, "ticket:write");

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold tracking-tight">Tickets</h1>
      <div className="flex flex-wrap items-end gap-3">
        <div className="w-56"><Field label="Search subject or #"><input className={inputCls} value={f.q} onChange={(e) => set("q", e.target.value)} /></Field></div>
        <Field label="Status">
          <select className={inputCls} value={f.status} onChange={(e) => set("status", e.target.value)}>
            <option value="">{f.open_only ? "Open" : "Any"}</option>
            {STATUSES.map((s) => <option key={s} value={s}>{STATUS_LABEL[s]}</option>)}
          </select>
        </Field>
        <Field label="Queue">
          <select className={inputCls} value={f.queue_id} onChange={(e) => set("queue_id", e.target.value)}>
            <option value="">Any</option>
            {lk.queues.map((q) => <option key={q.id} value={q.id}>{q.name}</option>)}
          </select>
        </Field>
        <Field label="Assignee">
          <select className={inputCls} value={f.assignee} onChange={(e) => set("assignee", e.target.value)}>
            <option value="">Anyone</option>
            <option value="me">Me</option>
            <option value="none">Unassigned</option>
          </select>
        </Field>
        <label className="flex items-center gap-1 pb-2 text-sm"><input type="checkbox" checked={f.open_only} onChange={(e) => set("open_only", e.target.checked)} />Open only</label>
        <label className="flex items-center gap-1 pb-2 text-sm"><input type="checkbox" checked={f.triage} onChange={(e) => set("triage", e.target.checked)} />Needs triage</label>
      </div>
      <ErrorMsg error={list.error} />
      {canWrite && selected.size > 0 && (
        <BulkBar ids={[...selected]} onDone={() => { setSelected(new Set()); qc.invalidateQueries({ queryKey: ["tickets"] }); }} />
      )}
      <TicketTable
        tickets={items}
        sort={sort}
        onSort={onSort}
        selected={canWrite ? selected : undefined}
        onToggle={canWrite ? toggle : undefined}
        onToggleAll={(on) => setSelected(on ? new Set(items.map((t) => t.id)) : new Set())}
      />
      <div className="flex items-center justify-between text-sm text-slate-500">
        <span>{total === 0 ? "No tickets" : `${offset + 1}–${Math.min(offset + PAGE, total)} of ${total}`}</span>
        <span className="flex gap-2">
          <Button variant="secondary" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>Previous</Button>
          <Button variant="secondary" disabled={offset + PAGE >= total} onClick={() => setOffset(offset + PAGE)}>Next</Button>
        </span>
      </div>
      {can(me, "ticket:write") && (
        <form className="grid gap-2 rounded-lg border border-slate-200 bg-surface p-4 sm:grid-cols-3" onSubmit={(e) => { e.preventDefault(); create.mutate(); }}>
          <h2 className="col-span-full font-semibold">New ticket</h2>
          <Field label="Organization">
            <select className={inputCls} required value={nt.organization_id} onChange={(e) => setNt({ ...nt, organization_id: e.target.value })}>
              <option value="">Select…</option>
              {orgs.data?.items.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
            </select>
          </Field>
          <div className="sm:col-span-2"><Field label="Subject"><input className={inputCls} required value={nt.subject} onChange={(e) => setNt({ ...nt, subject: e.target.value })} /></Field></div>
          <div className="col-span-full"><Field label="Description"><textarea className={inputCls} value={nt.description} onChange={(e) => setNt({ ...nt, description: e.target.value })} /></Field></div>
          <div className="col-span-full space-y-2"><ErrorMsg error={create.error} /><Button type="submit" disabled={create.isPending}>Create ticket</Button></div>
        </form>
      )}
    </div>
  );
}

function BulkBar({ ids, onDone }: { ids: number[]; onDone: () => void }) {
  const lk = useLookups();
  const [c, setC] = useState({ status: "", assignee_id: "", queue_id: "", priority_id: "" });
  const [result, setResult] = useState<BulkResult | null>(null);
  const changes = {
    ...(c.status && { status: c.status }),
    ...(c.assignee_id && { assignee_id: Number(c.assignee_id) }),
    ...(c.queue_id && { queue_id: Number(c.queue_id) }),
    ...(c.priority_id && { priority_id: Number(c.priority_id) }),
  };
  const apply = useMutation({
    mutationFn: (ch: object) => api<BulkResult>("/tickets/bulk", { method: "POST", json: { ticket_ids: ids, changes: ch } }),
    onSuccess: (r) => {
      setResult(r);
      if (r.failed.length === 0) onDone();
    },
  });
  const sel = (label: string, key: keyof typeof c, opts: { id: number | string; name: string }[]) => (
    <Field label={label}>
      <select className={inputCls} value={c[key]} onChange={(e) => setC({ ...c, [key]: e.target.value })}>
        <option value="">No change</option>
        {opts.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
      </select>
    </Field>
  );
  return (
    <div className="space-y-2 rounded-lg border border-blue-300 bg-blue-50 p-3" role="region" aria-label="Bulk actions">
      <div className="flex flex-wrap items-end gap-3">
        <b className="pb-2 text-sm">{ids.length} selected</b>
        {sel("Status", "status", STATUSES.map((s) => ({ id: s, name: STATUS_LABEL[s] })))}
        {sel("Assignee", "assignee_id", lk.techs.map((u) => ({ id: u.id, name: u.display_name })))}
        {sel("Queue", "queue_id", lk.queues.map((q) => ({ id: q.id, name: q.name })))}
        {sel("Priority", "priority_id", lk.priorities.map((p) => ({ id: p.id, name: p.name })))}
        <Button disabled={apply.isPending || Object.keys(changes).length === 0} onClick={() => apply.mutate(changes)}>Apply to {ids.length}</Button>
        <Button variant="secondary" disabled={apply.isPending} onClick={() => apply.mutate({ status: "closed" })}>Close {ids.length}</Button>
      </div>
      <ErrorMsg error={apply.error} />
      {result && result.failed.length > 0 && (
        <div className="text-sm text-red-700">
          {result.updated} updated, {result.failed.length} failed:
          <ul className="list-disc pl-5">{result.failed.map((f) => <li key={f.id}>Ticket id {f.id}: {f.error}</li>)}</ul>
          <Button variant="secondary" onClick={onDone}>Dismiss</Button>
        </div>
      )}
    </div>
  );
}
