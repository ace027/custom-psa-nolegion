import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { AppSettings, CannedResponse, CustomFieldDef, FieldType, Holiday, Lookup, TicketStatusRow, MailStatus, Priority, Queue, api } from "../api";
import RemindersCard from "./RemindersCard";
import { Button, Card, ErrorMsg, Field, fmt, inputCls } from "../ui";

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export default function Settings() {
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold tracking-tight">Settings</h1>
      <MailCard />
      <InvoicingCard />
      <RemindersCard />
      <PortalCard />
      <HoursCard />
      <StatusesCard />
      <TicketTypesCard />
      <HolidaysCard />
      <EmailAutomationCard />
      <SimpleList title="Queues" path="queues" defaults />
      <SimpleList title="Categories" path="categories" />
      <SimpleList title="Work types" path="work-types" />
      <SimpleList title="Internal time categories" path="time-categories" />
      <PrioritiesCard />
      <CannedCard />
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
      <p className="mt-2 text-xs text-slate-500">Changes apply to new tickets and future SLA calculations; existing due dates are recomputed only when a ticket's priority or pause state changes. Holidays work the same way.</p>
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

function PortalCard() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["lookup", "settings"], queryFn: () => api<AppSettings>("/settings") });
  const save = useMutation({
    mutationFn: (portal_enabled: boolean) => api("/settings", { method: "PATCH", json: { portal_enabled } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["lookup"] }),
  });
  if (!q.data) return null;
  return (
    <Card title="Client portal">
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={q.data.portal_enabled} onChange={(e) => save.mutate(e.target.checked)} />
        Turn the client portal on
      </label>
      <p className="mt-2 text-xs text-slate-500">Clients sign in at /portal with a one-time link emailed to a contact you have given portal access (Organizations &gt; contact). Needs the mailbox configured. Turning this off signs everyone out at once.</p>
      <ErrorMsg error={save.error} />
    </Card>
  );
}

function CannedCard() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["cfg", "canned-responses"], queryFn: () => api<CannedResponse[]>("/canned-responses?include_archived=true") });
  const [f, setF] = useState({ name: "", body: "" });
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["cfg", "canned-responses"] });
    qc.invalidateQueries({ queryKey: ["canned"] });
  };
  const add = useMutation({ mutationFn: () => api("/canned-responses", { method: "POST", json: f }), onSuccess: () => { setF({ name: "", body: "" }); refresh(); } });
  const act = useMutation({ mutationFn: ({ id, action }: { id: number; action: string }) => api(`/canned-responses/${id}/${action}`, { method: "POST" }), onSuccess: refresh });
  return (
    <Card title="Canned responses">
      <p className="mb-2 text-sm text-slate-600">Reusable replies for the note box. Placeholders: <code>{"{{contact_name}}"}</code>, <code>{"{{ticket_number}}"}</code>.</p>
      <ul className="divide-y divide-slate-100 text-sm">
        {q.data?.map((x) => (
          <li key={x.id} className="flex items-start justify-between gap-2 py-1.5">
            <span className={x.archived_at ? "text-slate-400 line-through" : ""}><b>{x.name}</b><span className="block whitespace-pre-wrap text-slate-600">{x.body}</span></span>
            <Button variant="secondary" onClick={() => act.mutate({ id: x.id, action: x.archived_at ? "unarchive" : "archive" })}>{x.archived_at ? "Restore" : "Archive"}</Button>
          </li>
        ))}
      </ul>
      <ErrorMsg error={add.error ?? act.error} />
      <form className="mt-2 space-y-2" onSubmit={(e) => { e.preventDefault(); add.mutate(); }}>
        <Field label="Name"><input className={inputCls} required value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
        <Field label="Text"><textarea className={inputCls} rows={3} required value={f.body} onChange={(e) => setF({ ...f, body: e.target.value })} /></Field>
        <Button type="submit">Add response</Button>
      </form>
    </Card>
  );
}

const hhmm = (m: number) => `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;

function HolidaysCard() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["cfg", "holidays"], queryFn: () => api<Holiday[]>("/holidays") });
  const [f, setF] = useState({ on_date: "", name: "", short: false, open: "09:00", close: "12:00" });
  const toMin = (v: string) => Number(v.slice(0, 2)) * 60 + Number(v.slice(3, 5));
  const refresh = () => qc.invalidateQueries({ queryKey: ["cfg", "holidays"] });
  const add = useMutation({
    mutationFn: () =>
      api("/holidays", {
        method: "POST",
        json: { on_date: f.on_date, name: f.name, open_minute: f.short ? toMin(f.open) : null, close_minute: f.short ? toMin(f.close) : null },
      }),
    onSuccess: () => { setF({ ...f, on_date: "", name: "" }); refresh(); },
  });
  const del = useMutation({ mutationFn: (id: number) => api(`/holidays/${id}`, { method: "DELETE" }), onSuccess: refresh });
  return (
    <Card title="Holidays">
      <p className="mb-2 text-sm text-slate-600">SLA clocks do not run on a closed day, and run only the shortened hours on a half day. Only affects business days. Tickets that already have a due date keep it until something recomputes it.</p>
      <ul className="divide-y divide-slate-100 text-sm">
        {q.data?.map((h) => (
          <li key={h.id} className="flex items-center justify-between py-1.5">
            <span>
              <b>{h.on_date}</b> {h.name}
              <span className="ml-2 text-slate-500">{h.open_minute === null || h.close_minute === null ? "closed" : `open ${hhmm(h.open_minute)}–${hhmm(h.close_minute)}`}</span>
            </span>
            <Button variant="secondary" onClick={() => del.mutate(h.id)}>Remove</Button>
          </li>
        ))}
        {q.data?.length === 0 && <li className="py-1.5 text-slate-500">No holidays yet.</li>}
      </ul>
      <ErrorMsg error={add.error ?? del.error} />
      <form className="mt-2 flex flex-wrap items-end gap-3" onSubmit={(e) => { e.preventDefault(); add.mutate(); }}>
        <Field label="Date"><input className={inputCls} type="date" required value={f.on_date} onChange={(e) => setF({ ...f, on_date: e.target.value })} /></Field>
        <Field label="Name"><input className={inputCls} required value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
        <label className="flex items-center gap-1 pb-2 text-sm"><input type="checkbox" checked={f.short} onChange={(e) => setF({ ...f, short: e.target.checked })} />Half day</label>
        {f.short && (
          <>
            <Field label="Opens"><input className={inputCls} type="time" value={f.open} onChange={(e) => setF({ ...f, open: e.target.value })} /></Field>
            <Field label="Closes"><input className={inputCls} type="time" value={f.close} onChange={(e) => setF({ ...f, close: e.target.value })} /></Field>
          </>
        )}
        <Button type="submit">Add holiday</Button>
      </form>
    </Card>
  );
}

function EmailAutomationCard() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["lookup", "settings"], queryFn: () => api<AppSettings>("/settings") });
  const [edit, setEdit] = useState<Partial<AppSettings> | null>(null);
  const save = useMutation({
    mutationFn: () => api("/settings", { method: "PATCH", json: { ...edit, escalation_email: edit?.escalation_email ?? undefined } }),
    onSuccess: () => { setEdit(null); qc.invalidateQueries({ queryKey: ["lookup"] }); },
  });
  if (!q.data) return null;
  const s = { ...q.data, ...edit };
  const upd = (p: Partial<AppSettings>) => setEdit({ ...edit, ...p });
  return (
    <Card title="Auto-acknowledgement and escalation">
      <div className="space-y-3">
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={s.auto_ack_enabled} onChange={(e) => upd({ auto_ack_enabled: e.target.checked })} />
          Email a confirmation when a known client emails in a new request
        </label>
        <p className="text-xs text-slate-500">Never sent to unknown senders, automated mail or replies; at most 3 per address per day; one per ticket. Placeholders: {"{ticket_number}"} {"{contact_name}"} {"{company}"} {"{subject}"}. The subject always keeps the [#number] tag so replies thread.</p>
        <Field label="Subject"><input className={inputCls} value={s.auto_ack_subject} onChange={(e) => upd({ auto_ack_subject: e.target.value })} /></Field>
        <Field label="Message"><textarea className={inputCls} rows={5} value={s.auto_ack_body} onChange={(e) => upd({ auto_ack_body: e.target.value })} /></Field>
        <Field label="When a ticket breaches its SLA, email this address (blank = off)">
          <input className={inputCls} type="email" value={s.escalation_email ?? ""} onChange={(e) => upd({ escalation_email: e.target.value })} />
        </Field>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={s.escalation_bump_priority} onChange={(e) => upd({ escalation_bump_priority: e.target.checked })} />
          Also raise the ticket's priority by one step
        </label>
        <p className="text-xs text-slate-500">Each ticket escalates once. Turning this on escalates tickets that are already breached.</p>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={s.csat_enabled} onChange={(e) => upd({ csat_enabled: e.target.checked })} />
          Email a satisfaction survey (1 to 5) when a ticket is first resolved
        </label>
        <p className="text-xs text-slate-500">One survey per ticket, only to the ticket's contact at a known client. Each link works once and expires after 30 days; the customer confirms on a page, so mail scanners cannot answer for them.</p>
      </div>
      <ErrorMsg error={save.error} />
      {edit && <div className="mt-2"><Button onClick={() => save.mutate()}>Save</Button></div>}
    </Card>
  );
}

const BEHAVIOR_LABEL: Record<string, string> = {
  new: "counts as New",
  open: "counts as Open",
  waiting_on_customer: "pauses the SLA clock (waiting)",
  resolved: "stops the SLA clock (resolved)",
  closed: "stops the SLA clock (closed)",
};

function StatusesCard() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["cfg", "ticket-statuses"], queryFn: () => api<TicketStatusRow[]>("/ticket-statuses?include_archived=true") });
  const [f, setF] = useState({ name: "", behavior: "open" });
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["cfg", "ticket-statuses"] });
    qc.invalidateQueries({ queryKey: ["lookup"] });
  };
  const add = useMutation({ mutationFn: () => api("/ticket-statuses", { method: "POST", json: f }), onSuccess: () => { setF({ ...f, name: "" }); refresh(); } });
  const act = useMutation({ mutationFn: ({ id, action }: { id: number; action: string }) => api(`/ticket-statuses/${id}/${action}`, { method: "POST" }), onSuccess: refresh });
  const rename = useMutation({ mutationFn: ({ id, name }: { id: number; name: string }) => api(`/ticket-statuses/${id}`, { method: "PATCH", json: { name } }), onSuccess: refresh });
  return (
    <Card title="Ticket statuses">
      <p className="mb-2 text-sm text-slate-600">Each status behaves like one of the five built-in states, chosen when you create it and fixed afterwards, so SLA clocks, reopening on customer replies, and the dashboard keep working.</p>
      <ul className="divide-y divide-slate-100 text-sm">
        {q.data?.map((x) => (
          <li key={x.id} className="flex items-center justify-between gap-2 py-1.5">
            <span className={x.archived_at ? "text-slate-400 line-through" : ""}>
              <b>{x.name}</b> <span className="text-slate-500">{BEHAVIOR_LABEL[x.behavior]}</span>
            </span>
            <span className="flex gap-2">
              <Button variant="secondary" onClick={() => { const name = window.prompt("Rename status", x.name); if (name) rename.mutate({ id: x.id, name }); }}>Rename</Button>
              <Button variant="secondary" onClick={() => act.mutate({ id: x.id, action: x.archived_at ? "unarchive" : "archive" })}>{x.archived_at ? "Restore" : "Archive"}</Button>
            </span>
          </li>
        ))}
      </ul>
      <ErrorMsg error={add.error ?? act.error ?? rename.error} />
      <form className="mt-2 flex flex-wrap items-end gap-3" onSubmit={(e) => { e.preventDefault(); add.mutate(); }}>
        <Field label="Name"><input className={inputCls} required value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
        <Field label="Behaves like">
          <select className={inputCls} value={f.behavior} onChange={(e) => setF({ ...f, behavior: e.target.value })}>
            {Object.entries(BEHAVIOR_LABEL).map(([k, v]) => <option key={k} value={k}>{k.replace(/_/g, " ")} ({v})</option>)}
          </select>
        </Field>
        <Button type="submit">Add status</Button>
      </form>
    </Card>
  );
}

const FIELD_TYPES: FieldType[] = ["text", "number", "date", "dropdown", "checkbox"];

function TicketTypesCard() {
  const qc = useQueryClient();
  const types = useQuery({ queryKey: ["cfg", "ticket-types"], queryFn: () => api<Lookup[]>("/ticket-types?include_archived=true") });
  const [open, setOpen] = useState<number | null>(null);
  const [name, setName] = useState("");
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["cfg"] });
    qc.invalidateQueries({ queryKey: ["lookup"] });
  };
  const add = useMutation({ mutationFn: () => api("/ticket-types", { method: "POST", json: { name } }), onSuccess: () => { setName(""); refresh(); } });
  const act = useMutation({ mutationFn: ({ id, action }: { id: number; action: string }) => api(`/ticket-types/${id}/${action}`, { method: "POST" }), onSuccess: refresh });
  const rename = useMutation({ mutationFn: ({ id, name }: { id: number; name: string }) => api(`/ticket-types/${id}`, { method: "PATCH", json: { name } }), onSuccess: refresh });
  return (
    <Card title="Ticket types and custom fields">
      <p className="mb-2 text-sm text-slate-600">A type (for example New hire) carries its own extra fields. Required fields are enforced when a ticket gets the type. Fields can be hidden but never deleted, so old tickets keep their answers.</p>
      <ul className="divide-y divide-slate-100 text-sm">
        {types.data?.map((x) => (
          <li key={x.id} className="py-1.5">
            <div className="flex items-center justify-between gap-2">
              <span className={x.archived_at ? "text-slate-400 line-through" : "font-semibold"}>{x.name}</span>
              <span className="flex gap-2">
                <Button variant="secondary" onClick={() => setOpen(open === x.id ? null : x.id)}>{open === x.id ? "Hide fields" : "Fields"}</Button>
                <Button variant="secondary" onClick={() => { const n = window.prompt("Rename type", x.name); if (n) rename.mutate({ id: x.id, name: n }); }}>Rename</Button>
                <Button variant="secondary" onClick={() => act.mutate({ id: x.id, action: x.archived_at ? "unarchive" : "archive" })}>{x.archived_at ? "Restore" : "Archive"}</Button>
              </span>
            </div>
            {open === x.id && <FieldsEditor typeId={x.id} typeArchived={!!x.archived_at} />}
          </li>
        ))}
      </ul>
      <ErrorMsg error={add.error ?? act.error ?? rename.error} />
      <form className="mt-2 flex items-end gap-3" onSubmit={(e) => { e.preventDefault(); add.mutate(); }}>
        <Field label="New type"><input className={inputCls} required value={name} onChange={(e) => setName(e.target.value)} /></Field>
        <Button type="submit">Add type</Button>
      </form>
    </Card>
  );
}

function FieldsEditor({ typeId, typeArchived }: { typeId: number; typeArchived: boolean }) {
  const qc = useQueryClient();
  const key = ["cfg", "fields", typeId];
  const q = useQuery({ queryKey: key, queryFn: () => api<CustomFieldDef[]>(`/ticket-types/${typeId}/fields?include_archived=true`) });
  const blank = { name: "", field_type: "text" as FieldType, options: "", required: false, client_visible: false };
  const [f, setF] = useState(blank);
  const refresh = () => qc.invalidateQueries({ queryKey: key });
  const add = useMutation({
    mutationFn: () => api(`/ticket-types/${typeId}/fields`, {
      method: "POST",
      json: { name: f.name, field_type: f.field_type, required: f.required, client_visible: f.client_visible, options: f.field_type === "dropdown" ? f.options.split(",").map((o) => o.trim()).filter(Boolean) : null },
    }),
    onSuccess: () => { setF(blank); refresh(); },
  });
  const patch = useMutation({ mutationFn: ({ id, json }: { id: number; json: Record<string, unknown> }) => api(`/custom-fields/${id}`, { method: "PATCH", json }), onSuccess: refresh });
  const act = useMutation({ mutationFn: ({ id, action }: { id: number; action: string }) => api(`/custom-fields/${id}/${action}`, { method: "POST" }), onSuccess: refresh });
  return (
    <div className="mt-2 rounded border border-slate-200 p-3">
      <ul className="divide-y divide-slate-100">
        {q.data?.map((d) => (
          <li key={d.id} className="flex flex-wrap items-center justify-between gap-2 py-1">
            <span className={d.archived_at ? "text-slate-400 line-through" : ""}>
              <b>{d.name}</b> <span className="text-slate-500">{d.field_type}{d.options ? ` (${d.options.join(", ")})` : ""}{d.required ? " · required" : ""}{d.client_visible ? " · shown to client" : ""}</span>
            </span>
            <span className="flex gap-2">
              <Button variant="secondary" onClick={() => patch.mutate({ id: d.id, json: { required: !d.required } })}>{d.required ? "Make optional" : "Make required"}</Button>
              <Button variant="secondary" onClick={() => patch.mutate({ id: d.id, json: { client_visible: !d.client_visible } })}>{d.client_visible ? "Hide from client" : "Show to client"}</Button>
              <Button variant="secondary" onClick={() => { const n = window.prompt("Rename field", d.name); if (n) patch.mutate({ id: d.id, json: { name: n } }); }}>Rename</Button>
              <Button variant="secondary" onClick={() => act.mutate({ id: d.id, action: d.archived_at ? "unarchive" : "archive" })}>{d.archived_at ? "Restore" : "Archive"}</Button>
            </span>
          </li>
        ))}
      </ul>
      <ErrorMsg error={add.error ?? patch.error ?? act.error} />
      {!typeArchived && (
        <form className="mt-2 flex flex-wrap items-end gap-3" onSubmit={(e) => { e.preventDefault(); add.mutate(); }}>
          <Field label="Field name"><input className={inputCls} required value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
          <Field label="Kind">
            <select className={inputCls} value={f.field_type} onChange={(e) => setF({ ...f, field_type: e.target.value as FieldType })}>
              {FIELD_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </Field>
          {f.field_type === "dropdown" && <Field label="Options (comma separated)"><input className={inputCls} required value={f.options} onChange={(e) => setF({ ...f, options: e.target.value })} /></Field>}
          <label className="flex items-center gap-1 pb-2 text-sm"><input type="checkbox" checked={f.required} onChange={(e) => setF({ ...f, required: e.target.checked })} />Required</label>
          <label className="flex items-center gap-1 pb-2 text-sm"><input type="checkbox" checked={f.client_visible} onChange={(e) => setF({ ...f, client_visible: e.target.checked })} />Show to client</label>
          <Button type="submit">Add field</Button>
        </form>
      )}
    </div>
  );
}
