import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { AppSettings, Lookup, MailStatus, Priority, Queue, api } from "../api";
import { Button, Card, ErrorMsg, Field, fmt, inputCls } from "../ui";

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export default function Settings() {
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Settings</h1>
      <MailCard />
      <InvoicingCard />
      <HoursCard />
      <SimpleList title="Queues" path="queues" defaults />
      <SimpleList title="Categories" path="categories" />
      <SimpleList title="Work types" path="work-types" />
      <PrioritiesCard />
    </div>
  );
}

function MailCard() {
  const q = useQuery({ queryKey: ["mail-status"], queryFn: () => api<MailStatus>("/mail/status"), refetchInterval: 30_000 });
  const s = q.data;
  return (
    <Card title="Mailbox connector">
      <ErrorMsg error={q.error} />
      {s && (
        <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm sm:grid-cols-4">
          <dt className="text-slate-500">Status</dt>
          <dd className={s.configured ? (s.last_error ? "text-red-700" : "text-green-700") : "text-amber-700"}>
            {!s.configured ? "Not configured" : s.last_error ? "Error" : "Working"}
          </dd>
          <dt className="text-slate-500">Mailbox</dt><dd>{s.mailbox ?? "—"}</dd>
          <dt className="text-slate-500">Worker last seen</dt>
          <dd className={!s.worker_seen_at || Date.now() - new Date(s.worker_seen_at).getTime() > 5 * 60_000 ? "text-red-700" : ""}>{s.worker_seen_at ? fmt(s.worker_seen_at) : "never (is the worker container running?)"}</dd>
          <dt className="text-slate-500">Last poll</dt><dd>{fmt(s.last_poll_at)}</dd>
          <dt className="text-slate-500">Last success</dt><dd>{fmt(s.last_success_at)}</dd>
          <dt className="text-slate-500">Emails ingested</dt><dd>{s.messages_ingested}</dd>
          <dt className="text-slate-500">Outbound pending / failed</dt><dd>{s.outbound_pending} / {s.outbound_failed}</dd>
          <dt className="text-slate-500">Tickets needing triage</dt><dd>{s.tickets_needing_triage}</dd>
        </dl>
      )}
      {s?.last_error && <p className="mt-2 rounded bg-red-50 p-2 text-sm text-red-700">{fmt(s.last_error_at)}: {s.last_error}</p>}
      {s && !s.configured && <p className="mt-2 text-sm text-slate-600">Email-to-ticket is off until the mailbox is configured. See docs/MAIL_SETUP.md.</p>}
    </Card>
  );
}

function HoursCard() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["lookup", "settings"], queryFn: () => api<AppSettings>("/settings") });
  const [edit, setEdit] = useState<AppSettings | null>(null);
  const s = edit ?? q.data;
  const save = useMutation({
    mutationFn: () => api("/settings", { method: "PATCH", json: edit }),
    onSuccess: () => {
      setEdit(null);
      qc.invalidateQueries();
    },
  });
  if (!s) return null;
  const hhmm = (m: number) => `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
  const toMin = (v: string) => Number(v.slice(0, 2)) * 60 + Number(v.slice(3, 5));
  const upd = (patch: Partial<AppSettings>) => setEdit({ ...s, ...patch });
  return (
    <Card title="Business hours, SLA and billing">
      <div className="grid gap-3 sm:grid-cols-4">
        <Field label="Time zone (IANA)"><input className={inputCls} value={s.timezone} onChange={(e) => upd({ timezone: e.target.value })} /></Field>
        <Field label="Opens"><input className={inputCls} type="time" value={hhmm(s.business_start_minute)} onChange={(e) => upd({ business_start_minute: toMin(e.target.value) })} /></Field>
        <Field label="Closes"><input className={inputCls} type="time" value={hhmm(s.business_end_minute)} onChange={(e) => upd({ business_end_minute: toMin(e.target.value) })} /></Field>
        <Field label="Billing increment (min)"><input className={inputCls} type="number" min={1} value={s.billing_increment_minutes} onChange={(e) => upd({ billing_increment_minutes: Number(e.target.value) })} /></Field>
        <Field label="'At risk' when this % of SLA time is left"><input className={inputCls} type="number" min={0} max={100} value={s.sla_at_risk_percent} onChange={(e) => upd({ sla_at_risk_percent: Number(e.target.value) })} /></Field>
        <div className="col-span-full flex gap-3 text-sm">
          {DAYS.map((d, i) => (
            <label key={d} className="flex items-center gap-1">
              <input type="checkbox" checked={s.business_days.includes(i)} onChange={(e) => upd({ business_days: e.target.checked ? [...s.business_days, i] : s.business_days.filter((x) => x !== i) })} />
              {d}
            </label>
          ))}
        </div>
      </div>
      <p className="mt-2 text-xs text-slate-500">Changes apply to new tickets and future SLA calculations; existing due dates are recomputed only when a ticket's priority or pause state changes.</p>
      <ErrorMsg error={save.error} />
      {edit && <div className="mt-2"><Button onClick={() => save.mutate()}>Save</Button></div>}
    </Card>
  );
}

function SimpleList({ title, path, defaults }: { title: string; path: string; defaults?: boolean }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["cfg", path], queryFn: () => api<(Lookup & Partial<Queue>)[]>(`/${path}?include_archived=true`) });
  const [name, setName] = useState("");
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["cfg", path] });
    qc.invalidateQueries({ queryKey: ["lookup"] });
  };
  const add = useMutation({ mutationFn: () => api(`/${path}`, { method: "POST", json: { name } }), onSuccess: () => { setName(""); refresh(); } });
  const act = useMutation({
    mutationFn: ({ id, action, json }: { id: number; action?: string; json?: object }) =>
      action ? api(`/${path}/${id}/${action}`, { method: "POST" }) : api(`/${path}/${id}`, { method: "PATCH", json }),
    onSuccess: refresh,
  });
  return (
    <Card title={title}>
      <ul className="divide-y divide-slate-100 text-sm">
        {q.data?.map((x) => (
          <li key={x.id} className="flex items-center justify-between py-1.5">
            <span className={x.archived_at ? "text-slate-400 line-through" : ""}>{x.name}{x.is_default && <b className="ml-2 text-xs text-blue-700">default</b>}</span>
            <span className="flex gap-2">
              {defaults && !x.is_default && !x.archived_at && <Button variant="secondary" onClick={() => act.mutate({ id: x.id, json: { is_default: true } })}>Make default</Button>}
              {!x.is_default && <Button variant="secondary" onClick={() => act.mutate({ id: x.id, action: x.archived_at ? "unarchive" : "archive" })}>{x.archived_at ? "Restore" : "Archive"}</Button>}
            </span>
          </li>
        ))}
      </ul>
      <ErrorMsg error={add.error ?? act.error} />
      <form className="mt-2 flex items-end gap-2" onSubmit={(e) => { e.preventDefault(); add.mutate(); }}>
        <Field label="Add"><input className={inputCls} required value={name} onChange={(e) => setName(e.target.value)} /></Field>
        <Button type="submit">Add</Button>
      </form>
    </Card>
  );
}

function PrioritiesCard() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["cfg", "priorities"], queryFn: () => api<Priority[]>("/priorities?include_archived=true") });
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["cfg", "priorities"] });
    qc.invalidateQueries({ queryKey: ["lookup"] });
  };
  const save = useMutation({ mutationFn: ({ id, json }: { id: number; json: object }) => api(`/priorities/${id}`, { method: "PATCH", json }), onSuccess: refresh });
  const [n, setN] = useState({ name: "", rank: "5", fr: "", res: "" });
  const add = useMutation({
    mutationFn: () => api("/priorities", { method: "POST", json: { name: n.name, rank: Number(n.rank), first_response_minutes: n.fr ? Number(n.fr) : null, resolution_minutes: n.res ? Number(n.res) : null } }),
    onSuccess: () => { setN({ name: "", rank: "5", fr: "", res: "" }); refresh(); },
  });
  const num = (v: string) => (v === "" ? null : Number(v));
  return (
    <Card title="Priorities and SLA targets (business minutes)">
      <table className="w-full text-left text-sm">
        <thead className="text-slate-500"><tr><th>Name</th><th>Rank</th><th>First response</th><th>Resolution</th><th /></tr></thead>
        <tbody>
          {q.data?.map((p) => (
            <tr key={p.id} className="border-t border-slate-100">
              <td className={p.archived_at ? "text-slate-400 line-through" : ""}>{p.name}{p.is_default && <b className="ml-2 text-xs text-blue-700">default</b>}</td>
              <td>{p.rank}</td>
              <td><input aria-label={`${p.name} first response`} className={inputCls + " w-24"} type="number" defaultValue={p.first_response_minutes ?? ""} onBlur={(e) => num(e.target.value) !== p.first_response_minutes && save.mutate({ id: p.id, json: { first_response_minutes: num(e.target.value) } })} /></td>
              <td><input aria-label={`${p.name} resolution`} className={inputCls + " w-24"} type="number" defaultValue={p.resolution_minutes ?? ""} onBlur={(e) => num(e.target.value) !== p.resolution_minutes && save.mutate({ id: p.id, json: { resolution_minutes: num(e.target.value) } })} /></td>
              <td>{!p.is_default && !p.archived_at && <Button variant="secondary" onClick={() => save.mutate({ id: p.id, json: { is_default: true } })}>Make default</Button>}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <ErrorMsg error={save.error ?? add.error} />
      <form className="mt-3 flex flex-wrap items-end gap-2" onSubmit={(e) => { e.preventDefault(); add.mutate(); }}>
        <Field label="Name"><input className={inputCls} required value={n.name} onChange={(e) => setN({ ...n, name: e.target.value })} /></Field>
        <div className="w-20"><Field label="Rank"><input className={inputCls} type="number" min={1} value={n.rank} onChange={(e) => setN({ ...n, rank: e.target.value })} /></Field></div>
        <div className="w-32"><Field label="First response"><input className={inputCls} type="number" min={1} value={n.fr} onChange={(e) => setN({ ...n, fr: e.target.value })} /></Field></div>
        <div className="w-32"><Field label="Resolution"><input className={inputCls} type="number" min={1} value={n.res} onChange={(e) => setN({ ...n, res: e.target.value })} /></Field></div>
        <Button type="submit">Add priority</Button>
      </form>
    </Card>
  );
}


function InvoicingCard() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["lookup", "settings"], queryFn: () => api<AppSettings>("/settings") });
  const [edit, setEdit] = useState<Partial<AppSettings>>({});
  const save = useMutation({
    mutationFn: () => api("/settings", { method: "PATCH", json: edit }),
    onSuccess: () => { setEdit({}); qc.invalidateQueries(); },
  });
  if (!q.data) return null;
  const v = { ...q.data, ...edit };
  return (
    <Card title="Invoicing: your company details">
      <p className="mb-2 text-sm text-slate-600">Printed on every invoice PDF. They are copied onto each invoice when it is finalized, so later changes never alter old invoices. Finalizing is blocked until a company name is set.</p>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Company name"><input className={inputCls} value={v.company_name ?? ""} onChange={(e) => setEdit({ ...edit, company_name: e.target.value })} /></Field>
        <Field label="Company address"><textarea className={inputCls} rows={2} value={v.company_address ?? ""} onChange={(e) => setEdit({ ...edit, company_address: e.target.value })} /></Field>
        <div className="sm:col-span-2"><Field label="Invoice footer (payment instructions, thank-you...)"><textarea className={inputCls} rows={2} value={v.invoice_footer ?? ""} onChange={(e) => setEdit({ ...edit, invoice_footer: e.target.value })} /></Field></div>
      </div>
      <ErrorMsg error={save.error} />
      {Object.keys(edit).length > 0 && <div className="mt-2"><Button onClick={() => save.mutate()}>Save</Button></div>}
    </Card>
  );
}
