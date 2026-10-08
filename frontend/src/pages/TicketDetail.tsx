import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useParams } from "react-router-dom";
import {
  Attachment, CannedResponse, Charge, CustomFieldDef, Contact, Note, Organization, Page, Product, Ticket, TimeEntry, api,
} from "../api";
import { can, useMe } from "../auth";
import { useLookups } from "../lookups";
import { money } from "../money";
import { Button, Card, ErrorMsg, Field, SlaBadge, fmt, inputCls } from "../ui";

export default function TicketDetail() {
  const id = Number(useParams().id);
  const { data: me } = useMe();
  const qc = useQueryClient();
  const refresh = () => qc.invalidateQueries();
  const canWrite = can(me, "ticket:write");

  const ticket = useQuery({ queryKey: ["ticket", id], queryFn: () => api<Ticket>(`/tickets/${id}`) });
  const notes = useQuery({ queryKey: ["notes", id], queryFn: () => api<Note[]>(`/tickets/${id}/notes`) });
  const time = useQuery({ queryKey: ["time", id], queryFn: () => api<TimeEntry[]>(`/tickets/${id}/time`) });
  const files = useQuery({ queryKey: ["files", id], queryFn: () => api<Attachment[]>(`/tickets/${id}/attachments`) });

  const t = ticket.data;
  if (ticket.isLoading) return <p>Loading…</p>;
  if (!t) return <ErrorMsg error={ticket.error ?? "Not found"} />;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-bold tracking-tight">
          #{t.number} {t.subject}
        </h1>
        <SlaBadge state={t.sla_state} />
      </div>
      <p className="text-sm text-slate-600">
        {t.needs_triage ? "Unmatched sender" : t.organization_name}
        {t.contact_name ? ` · ${t.contact_name}` : t.requester_email ? ` · ${t.requester_email}` : ""}
        {" · "}opened {fmt(t.created_at)} via {t.source}
      </p>
      {t.needs_triage && canWrite && <TriagePanel ticket={t} onDone={refresh} />}
      <Fields ticket={t} canWrite={canWrite} onDone={refresh} />
      <CustomFieldsCard key={`${t.id}-${t.type_id ?? 0}-${t.updated_at}`} ticket={t} canWrite={canWrite} onDone={refresh} />
      {t.description && (
        <Card title="Description">
          <p className="whitespace-pre-wrap text-sm">{t.description}</p>
        </Card>
      )}
      <NotesCard ticket={t} notes={notes.data ?? []} canWrite={canWrite} onDone={refresh} />
      <TimeCard ticket={t} entries={time.data ?? []} canWrite={can(me, "time:write")} meId={me?.id ?? 0} isAdmin={me?.role === "admin"} onDone={refresh} />
      {can(me, "billing:read") && !t.needs_triage && <ChargesCard ticket={t} canWrite={can(me, "charge:write")} onDone={refresh} />}
      {(files.data?.length ?? 0) > 0 && (
        <Card title="Attachments">
          <ul className="text-sm">
            {files.data!.map((a) => (
              <li key={a.id}>
                <a className="text-blue-700 hover:underline" href={`/api/attachments/${a.id}/download`}>
                  {a.filename}
                </a>{" "}
                <span className="text-slate-500">({Math.ceil(a.size_bytes / 1024)} KB)</span>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}

function Fields({ ticket: t, canWrite, onDone }: { ticket: Ticket; canWrite: boolean; onDone: () => void }) {
  const lk = useLookups();
  const patch = useMutation({
    mutationFn: (json: Record<string, unknown>) => api(`/tickets/${t.id}`, { method: "PATCH", json }),
    onSuccess: onDone,
  });
  // active statuses, plus the ticket's own if it has since been archived
  const statusOptions = [
    ...lk.statuses.filter((x) => !x.archived_at || x.id === t.status_id).map((x) => ({ id: x.id, name: x.name })),
  ];
  if (statusOptions.length === 0 && t.status_id) statusOptions.push({ id: t.status_id, name: t.status_name ?? t.status });
  const sel = (label: string, value: string | number | null, opts: { id: number | string; name: string }[], key: string, blank?: string) => (
    <Field label={label}>
      <select
        className={inputCls}
        disabled={!canWrite}
        value={value ?? ""}
        onChange={(e) => patch.mutate({ [key]: e.target.value === "" ? null : Number(e.target.value) })}
      >
        {blank !== undefined && <option value="">{blank}</option>}
        {opts.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
      </select>
    </Field>
  );
  return (
    <Card title="Details">
      <div className="grid gap-3 sm:grid-cols-3">
        {sel("Status", t.status_id ?? null, statusOptions, "status_id")}
        {sel("Assignee", t.assignee_id, lk.techs.map((u) => ({ id: u.id, name: u.display_name })), "assignee_id", "Unassigned")}
        {sel("Priority", t.priority_id, lk.priorities.map((p) => ({ id: p.id, name: p.name })), "priority_id")}
        {sel("Queue", t.queue_id, lk.queues.map((q) => ({ id: q.id, name: q.name })), "queue_id")}
        {sel("Category", t.category_id, lk.categories.map((c) => ({ id: c.id, name: c.name })), "category_id", "None")}
        <div className="text-sm">
          <div className="font-medium text-slate-700">SLA</div>
          <div className="text-slate-600">First response due: {fmt(t.sla_first_response_due)}{t.first_responded_at ? " (met)" : ""}</div>
          <div className="text-slate-600">Resolution due: {fmt(t.sla_resolution_due)}</div>
        </div>
      </div>
      <div className="mt-2"><ErrorMsg error={patch.error} /></div>
    </Card>
  );
}

function CustomFieldsCard({ ticket: t, canWrite, onDone }: { ticket: Ticket; canWrite: boolean; onDone: () => void }) {
  const lk = useLookups();
  const [typeId, setTypeId] = useState<string>(t.type_id ? String(t.type_id) : "");
  const [vals, setVals] = useState<Record<string, unknown>>({});
  const defs = useQuery({
    queryKey: ["type-fields", typeId],
    enabled: !!typeId,
    queryFn: () => api<CustomFieldDef[]>(`/ticket-types/${typeId}/fields`),
  });
  const stored = t.custom_values ?? {};
  const current = (id: number) => (String(id) in vals ? vals[String(id)] : stored[String(id)]);
  const save = useMutation({
    mutationFn: () => api(`/tickets/${t.id}`, { method: "PATCH", json: { type_id: typeId ? Number(typeId) : null, custom_values: vals } }),
    onSuccess: () => { setVals({}); onDone(); },
  });
  const types = lk.ticketTypes.filter((x) => !x.archived_at || x.id === t.type_id);
  if (types.length === 0 && !t.type_id) return null;
  const input = (d: CustomFieldDef) => {
    const v = current(d.id);
    const set = (x: unknown) => setVals({ ...vals, [String(d.id)]: x });
    if (d.field_type === "checkbox") return <input type="checkbox" disabled={!canWrite} checked={v === true} onChange={(e) => set(e.target.checked)} />;
    if (d.field_type === "dropdown")
      return (
        <select className={inputCls} disabled={!canWrite} value={String(v ?? "")} onChange={(e) => set(e.target.value)}>
          <option value="">—</option>
          {d.options?.map((o) => <option key={o} value={o}>{o}</option>)}
        </select>
      );
    return (
      <input
        className={inputCls}
        disabled={!canWrite}
        type={d.field_type === "number" ? "number" : d.field_type === "date" ? "date" : "text"}
        step="any"
        value={String(v ?? "")}
        onChange={(e) => set(d.field_type === "number" && e.target.value !== "" ? Number(e.target.value) : e.target.value)}
      />
    );
  };
  return (
    <Card title="Type and custom fields">
      <div className="grid gap-3 sm:grid-cols-3">
        <Field label="Type">
          <select className={inputCls} disabled={!canWrite} value={typeId} onChange={(e) => { setTypeId(e.target.value); setVals({}); }}>
            <option value="">None</option>
            {types.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
          </select>
        </Field>
        {defs.data?.map((d) => (
          <Field key={d.id} label={`${d.name}${d.required ? " *" : ""}`}>{input(d)}</Field>
        ))}
      </div>
      {canWrite && (
        <div className="mt-2"><Button disabled={save.isPending} onClick={() => save.mutate()}>Save type and fields</Button></div>
      )}
      <div className="mt-2"><ErrorMsg error={save.error} /></div>
    </Card>
  );
}

function TriagePanel({ ticket: t, onDone }: { ticket: Ticket; onDone: () => void }) {
  const [orgId, setOrgId] = useState("");
  const [contactId, setContactId] = useState("");
  const orgs = useQuery({ queryKey: ["orgs", "", false], queryFn: () => api<Page<Organization>>("/organizations?limit=200&include_archived=false&q=") });
  const contacts = useQuery({
    queryKey: ["contacts", Number(orgId)],
    enabled: !!orgId,
    queryFn: () => api<Contact[]>(`/organizations/${orgId}/contacts?include_archived=false`),
  });
  const save = useMutation({
    mutationFn: () => api(`/tickets/${t.id}`, { method: "PATCH", json: { organization_id: Number(orgId), contact_id: contactId ? Number(contactId) : null } }),
    onSuccess: onDone,
  });
  return (
    <div className="rounded-lg border border-amber-300 bg-amber-50 p-4">
      <h2 className="mb-1 font-semibold">Needs triage</h2>
      <p className="mb-3 text-sm">
        This ticket came from <b>{t.requester_email}</b>, who is not a known contact. Choose the organization it belongs to (this can only be set once).
      </p>
      <div className="flex flex-wrap items-end gap-3">
        <Field label="Organization">
          <select className={inputCls} value={orgId} onChange={(e) => { setOrgId(e.target.value); setContactId(""); }}>
            <option value="">Select…</option>
            {orgs.data?.items.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
          </select>
        </Field>
        <Field label="Contact (optional)">
          <select className={inputCls} value={contactId} onChange={(e) => setContactId(e.target.value)} disabled={!orgId}>
            <option value="">—</option>
            {contacts.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </Field>
        <Button disabled={!orgId || save.isPending} onClick={() => save.mutate()}>Assign</Button>
      </div>
      <ErrorMsg error={save.error} />
    </div>
  );
}

/** Replaces {{name}} placeholders; unknown ones are left visible so the tech notices them. */
export function fillCanned(body: string, vars: Record<string, string>): string {
  return body.replace(/\{\{\s*(\w+)\s*\}\}/g, (m, k: string) => vars[k] ?? m);
}

function NotesCard({ ticket: t, notes, canWrite, onDone }: { ticket: Ticket; notes: Note[]; canWrite: boolean; onDone: () => void }) {
  const [body, setBody] = useState("");
  const [visibility, setVisibility] = useState<"internal" | "customer">("internal");
  const [email, setEmail] = useState(false);
  const canned = useQuery({ queryKey: ["canned"], enabled: canWrite, queryFn: () => api<CannedResponse[]>("/canned-responses") });
  const insertCanned = (id: string) => {
    const c = canned.data?.find((x) => String(x.id) === id);
    if (!c) return;
    const text = fillCanned(c.body, { contact_name: t.contact_name ?? "there", ticket_number: String(t.number) });
    setBody(body ? `${body}\n${text}` : text);
  };
  const add = useMutation({
    mutationFn: () => api("/tickets/" + t.id + "/notes", { method: "POST", json: { body, visibility, send_email: email && visibility === "customer" } }),
    onSuccess: () => {
      setBody("");
      setEmail(false);
      onDone();
    },
  });
  return (
    <Card title="Notes">
      <ul className="space-y-2">
        {notes.map((n) => (
          <li key={n.id} className={`rounded border p-3 text-sm ${n.visibility === "internal" ? "border-amber-200 bg-amber-50" : "border-slate-200 bg-surface"}`}>
            <div className="mb-1 flex flex-wrap justify-between gap-2 text-xs text-slate-500">
              <span>
                <b>{n.author_name ?? n.author_email ?? "system"}</b> · {n.source === "email" ? "email from customer" : n.visibility === "internal" ? "internal note" : "visible to customer"}
                {n.email_status && n.source !== "email" && ` · email ${n.email_status}`}
              </span>
              <span>{fmt(n.created_at)}</span>
            </div>
            <p className="whitespace-pre-wrap">{n.body}</p>
          </li>
        ))}
        {notes.length === 0 && <li className="text-sm text-slate-500">No notes yet.</li>}
      </ul>
      {canWrite && (
        <form className="mt-3 space-y-2" onSubmit={(e) => { e.preventDefault(); add.mutate(); }}>
          {(canned.data?.length ?? 0) > 0 && (
            <select aria-label="Insert canned response" className={inputCls} value="" onChange={(e) => insertCanned(e.target.value)}>
              <option value="">Insert canned response…</option>
              {canned.data!.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          )}
          <textarea aria-label="Add a note" className={inputCls} rows={3} required value={body} onChange={(e) => setBody(e.target.value)} />
          <div className="flex flex-wrap items-center gap-4 text-sm">
            <label className="flex items-center gap-1"><input type="radio" checked={visibility === "internal"} onChange={() => setVisibility("internal")} />Internal</label>
            <label className="flex items-center gap-1"><input type="radio" checked={visibility === "customer"} onChange={() => setVisibility("customer")} />Visible to customer</label>
            {visibility === "customer" && (
              <label className="flex items-center gap-1"><input type="checkbox" checked={email} onChange={(e) => setEmail(e.target.checked)} />Email it to the customer</label>
            )}
            <Button type="submit" disabled={add.isPending}>Add note</Button>
          </div>
          <ErrorMsg error={add.error} />
        </form>
      )}
    </Card>
  );
}

function TimeCard({ ticket: t, entries, canWrite, meId, isAdmin, onDone }: { ticket: Ticket; entries: TimeEntry[]; canWrite: boolean; meId: number; isAdmin: boolean; onDone: () => void }) {
  const lk = useLookups();
  const [f, setF] = useState({ work_type_id: "", minutes: "", note: "", billable: true });
  const add = useMutation({
    mutationFn: () => api(`/tickets/${t.id}/time`, { method: "POST", json: { work_type_id: Number(f.work_type_id), minutes: Number(f.minutes), note: f.note || null, billable: f.billable } }),
    onSuccess: () => {
      setF({ ...f, minutes: "", note: "" });
      onDone();
    },
  });
  const voidIt = useMutation({ mutationFn: (id: number) => api(`/time-entries/${id}/void`, { method: "POST" }), onSuccess: onDone });
  const total = entries.reduce((s, e) => s + e.minutes_billable, 0);
  return (
    <Card title="Time">
      <table className="w-full text-left text-sm">
        <thead className="text-slate-500"><tr><th>Date</th><th>Type</th><th>Actual</th><th>Billable</th><th>Note</th><th /></tr></thead>
        <tbody>
          {entries.map((e) => (
            <tr key={e.id} className="border-t border-slate-100">
              <td>{e.work_date}</td>
              <td>{lk.workTypes.find((w) => w.id === e.work_type_id)?.name}</td>
              <td>{e.minutes_actual} min</td>
              <td>{e.billable ? `${e.minutes_billable} min` : "non-billable"}</td>
              <td>{e.note}</td>
              <td>{canWrite && (isAdmin || e.user_id === meId) && <button className="text-red-700 hover:underline" onClick={() => voidIt.mutate(e.id)}>Void</button>}</td>
            </tr>
          ))}
          {entries.length === 0 && <tr><td colSpan={6} className="text-slate-500">No time logged.</td></tr>}
        </tbody>
      </table>
      <p className="mt-1 text-sm text-slate-600">Total billable: <b>{total} min</b> ({(total / 60).toFixed(2)} h). Billable time rounds up to {lk.settings?.billing_increment_minutes ?? 15}-minute increments.</p>
      <ErrorMsg error={add.error ?? voidIt.error} />
      {canWrite && !t.needs_triage && (
        <form className="mt-3 flex flex-wrap items-end gap-2" onSubmit={(e) => { e.preventDefault(); add.mutate(); }}>
          <Field label="Work type">
            <select className={inputCls} required value={f.work_type_id} onChange={(e) => setF({ ...f, work_type_id: e.target.value })}>
              <option value="">Select…</option>
              {lk.workTypes.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
            </select>
          </Field>
          <div className="w-24"><Field label="Minutes"><input className={inputCls} type="number" min={1} max={1440} required value={f.minutes} onChange={(e) => setF({ ...f, minutes: e.target.value })} /></Field></div>
          <div className="w-64"><Field label="Note"><input className={inputCls} value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} /></Field></div>
          <label className="flex items-center gap-1 pb-2 text-sm"><input type="checkbox" checked={f.billable} onChange={(e) => setF({ ...f, billable: e.target.checked })} />Billable</label>
          <Button type="submit" disabled={add.isPending}>Log time</Button>
        </form>
      )}
      {t.needs_triage && <p className="mt-2 text-sm text-amber-700">Assign an organization before logging time.</p>}
    </Card>
  );
}


function ChargesCard({ ticket: t, canWrite, onDone }: { ticket: Ticket; canWrite: boolean; onDone: () => void }) {
  const charges = useQuery({ queryKey: ["charges", t.id], queryFn: () => api<Charge[]>(`/product-charges?ticket_id=${t.id}`) });
  const products = useQuery({ queryKey: ["products", "active"], queryFn: () => api<Product[]>("/products") });
  const [f, setF] = useState({ product_id: "", quantity: "1" });
  const add = useMutation({
    mutationFn: () => api("/product-charges", { method: "POST", json: { organization_id: t.organization_id, ticket_id: t.id, product_id: Number(f.product_id), quantity: f.quantity } }),
    onSuccess: () => { setF({ product_id: "", quantity: "1" }); onDone(); },
  });
  const voidIt = useMutation({ mutationFn: (id: number) => api(`/product-charges/${id}/void`, { method: "POST" }), onSuccess: onDone });
  const live = (charges.data ?? []).filter((c) => !c.voided_at);
  return (
    <Card title="Parts and products">
      <ul className="text-sm">
        {live.map((c) => (
          <li key={c.id} className="flex justify-between border-t border-slate-100 py-1">
            <span>{Number(c.quantity)} × {c.description} @ {money(c.unit_price_cents)}{c.invoice_line_id ? " · invoiced" : ""}</span>
            {!c.invoice_line_id && canWrite && <button className="text-red-700 hover:underline" onClick={() => voidIt.mutate(c.id)}>Void</button>}
          </li>
        ))}
        {live.length === 0 && <li className="text-slate-500">None. Products sold on this ticket go on the client's next invoice.</li>}
      </ul>
      <ErrorMsg error={add.error ?? voidIt.error} />
      {canWrite && (
        <form className="mt-2 flex flex-wrap items-end gap-2" onSubmit={(e) => { e.preventDefault(); add.mutate(); }}>
          <Field label="Product"><select className={inputCls} required value={f.product_id} onChange={(e) => setF({ ...f, product_id: e.target.value })}><option value="">Select…</option>{products.data?.map((p) => <option key={p.id} value={p.id}>{p.name} ({money(p.unit_price_cents)})</option>)}</select></Field>
          <div className="w-20"><Field label="Qty"><input className={inputCls} value={f.quantity} onChange={(e) => setF({ ...f, quantity: e.target.value })} /></Field></div>
          <Button type="submit">Add to ticket</Button>
        </form>
      )}
    </Card>
  );
}
