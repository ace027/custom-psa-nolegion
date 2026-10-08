import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Organization, Page, STATUSES, STATUS_LABEL, Ticket, api } from "../api";
import { can, useMe } from "../auth";
import { useLookups } from "../lookups";
import { Button, ErrorMsg, Field, inputCls } from "../ui";
import TicketTable from "./TicketTable";

export default function Tickets() {
  const { data: me } = useMe();
  const nav = useNavigate();
  const qc = useQueryClient();
  const lk = useLookups();
  const [f, setF] = useState({ q: "", status: "", queue_id: "", assignee: "", open_only: true, triage: false });
  const params = new URLSearchParams({ limit: "100" });
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
  const set = (k: string, v: string | boolean) => setF({ ...f, [k]: v });

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
      <TicketTable tickets={list.data?.items ?? []} />
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
