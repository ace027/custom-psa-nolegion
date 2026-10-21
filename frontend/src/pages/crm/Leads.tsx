import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Lead, LeadStatus, User, api, crmApi } from "../../api";
import { can, useMe } from "../../auth";
import { money, parseMoney } from "../../money";
import { Button, Card, ErrorMsg, Field, inputCls } from "../../ui";

const STATUSES: Exclude<LeadStatus, "converted">[] = ["new", "contacted", "qualified", "disqualified"];
const STATUS_LABEL: Record<LeadStatus, string> = {
  new: "New", contacted: "Contacted", qualified: "Qualified", disqualified: "Disqualified", converted: "Converted",
};

export default function Leads() {
  const { data: me } = useMe();
  const write = can(me, "crm:write");
  const qc = useQueryClient();
  const [status, setStatus] = useState("");
  const [search, setSearch] = useState("");
  const [adding, setAdding] = useState(false);
  const [converting, setConverting] = useState<Lead | null>(null);
  const users = useQuery({ queryKey: ["users"], queryFn: () => api<User[]>("/users"), enabled: write });
  const leads = useQuery({ queryKey: ["crm", "leads", status, search], queryFn: () => crmApi.leads({ status, q: search }) });
  const setLeadStatus = useMutation({
    mutationFn: ({ id, s }: { id: number; s: Exclude<LeadStatus, "converted"> }) => crmApi.updateLead(id, { status: s }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["crm", "leads"] }),
  });
  const rows = leads.data ?? [];
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <Field label="Status">
          <select className={inputCls} value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">All</option>
            {[...STATUSES, "converted" as const].map((s) => <option key={s} value={s}>{STATUS_LABEL[s]}</option>)}
          </select>
        </Field>
        <Field label="Search"><input type="search" className={inputCls} value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Name, company or email" /></Field>
        {write && <Button onClick={() => setAdding(!adding)}>{adding ? "Close" : "Add lead"}</Button>}
      </div>
      {write && adding && <LeadForm users={users.data ?? []} onDone={() => { setAdding(false); qc.invalidateQueries({ queryKey: ["crm", "leads"] }); }} />}
      {write && converting && <ConvertForm lead={converting} onClose={() => setConverting(null)} />}
      <ErrorMsg error={leads.error ?? setLeadStatus.error} />
      {leads.data && rows.length === 0 && <p className="text-sm text-slate-500">No leads yet.</p>}
      {rows.length > 0 && (
        <table className="w-full text-sm">
          <caption className="sr-only">Sales leads</caption>
          <thead>
            <tr className="border-b border-slate-200 text-left text-slate-500">
              <th scope="col" className="py-1.5">Name</th><th scope="col">Company</th><th scope="col">Contact</th>
              <th scope="col">Source</th><th scope="col">Owner</th><th scope="col">Status</th><th scope="col"><span className="sr-only">Actions</span></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((l) => (
              <tr key={l.id} className="border-b border-slate-100 align-top">
                <td className="py-1.5 font-medium">{l.name}</td>
                <td>{l.company ?? "—"}</td>
                <td>{[l.email, l.phone].filter(Boolean).join(" · ") || "—"}</td>
                <td>{l.source ?? "—"}</td>
                <td>{l.owner_name ?? "—"}</td>
                <td>
                  {write && l.status !== "converted" ? (
                    <select aria-label={`Status of ${l.name}`} className={inputCls} value={l.status} disabled={setLeadStatus.isPending}
                      onChange={(e) => setLeadStatus.mutate({ id: l.id, s: e.target.value as Exclude<LeadStatus, "converted"> })}>
                      {STATUSES.map((s) => <option key={s} value={s}>{STATUS_LABEL[s]}</option>)}
                    </select>
                  ) : STATUS_LABEL[l.status]}
                </td>
                <td className="text-right">
                  {l.converted_organization_id ? (
                    <Link className="text-blue-700 hover:underline" to={`/organizations/${l.converted_organization_id}`}>View client</Link>
                  ) : write && l.status === "qualified" ? (
                    <Button variant="secondary" onClick={() => setConverting(l)} aria-label={`Convert ${l.name}`}>Convert</Button>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function LeadForm({ users, onDone }: { users: User[]; onDone: () => void }) {
  const [f, setF] = useState({ name: "", company: "", email: "", phone: "", source: "", owner_id: "", notes: "" });
  const add = useMutation({
    mutationFn: () => crmApi.createLead({
      name: f.name.trim(),
      company: f.company.trim() || null,
      email: f.email.trim() || null,
      phone: f.phone.trim() || null,
      source: f.source.trim() || null,
      owner_id: f.owner_id ? Number(f.owner_id) : null,
      notes: f.notes.trim() || null,
    }),
    onSuccess: onDone,
  });
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
  const submit = (e: FormEvent) => { e.preventDefault(); add.mutate(); };
  return (
    <Card title="New lead">
      <form onSubmit={submit} className="grid gap-3 sm:grid-cols-3">
        <Field label="Name"><input required className={inputCls} value={f.name} onChange={set("name")} /></Field>
        <Field label="Company"><input className={inputCls} value={f.company} onChange={set("company")} /></Field>
        <Field label="Email"><input type="email" className={inputCls} value={f.email} onChange={set("email")} /></Field>
        <Field label="Phone"><input className={inputCls} value={f.phone} onChange={set("phone")} /></Field>
        <Field label="Source"><input className={inputCls} value={f.source} onChange={set("source")} placeholder="Referral, website…" /></Field>
        <Field label="Owner">
          <select className={inputCls} value={f.owner_id} onChange={set("owner_id")}>
            <option value="">Unowned</option>
            {users.filter((u) => u.is_active && (u.role === "admin" || u.role === "tech")).map((u) => <option key={u.id} value={u.id}>{u.display_name}</option>)}
          </select>
        </Field>
        <div className="sm:col-span-3"><Field label="Notes"><textarea className={inputCls} rows={2} value={f.notes} onChange={set("notes")} /></Field></div>
        <div className="sm:col-span-3 space-y-2">
          <ErrorMsg error={add.error} />
          <Button type="submit" disabled={add.isPending || !f.name.trim()}>Save lead</Button>
        </div>
      </form>
    </Card>
  );
}

function ConvertForm({ lead, onClose }: { lead: Lead; onClose: () => void }) {
  const qc = useQueryClient();
  const nav = useNavigate();
  const [name, setName] = useState(`${lead.company || lead.name} – new agreement`);
  const [monthly, setMonthly] = useState("0.00");
  const [term, setTerm] = useState("12");
  const [close, setClose] = useState("");
  const [notes, setNotes] = useState(lead.notes ?? "");
  const [bad, setBad] = useState("");
  const convert = useMutation({
    mutationFn: (json: Parameters<typeof crmApi.convertLead>[1]) => crmApi.convertLead(lead.id, json),
    onSuccess: (o) => {
      qc.invalidateQueries({ queryKey: ["crm"] });
      qc.invalidateQueries({ queryKey: ["organizations"] });
      nav(`/crm/opportunities/${o.id}`);
    },
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const cents = parseMoney(monthly);
    const months = Number(term);
    if (cents === null || cents < 0) return setBad("Enter the monthly amount, for example 1500.00.");
    if (!Number.isInteger(months) || months < 1 || months > 120) return setBad("Term must be 1 to 120 months.");
    setBad("");
    convert.mutate({ name: name.trim() || undefined, monthly_cents: cents, term_months: months, expected_close_date: close || null, notes: notes.trim() || null });
  };
  return (
    <Card title={`Convert ${lead.name}`} actions={<Button variant="secondary" onClick={onClose}>Cancel</Button>}>
      <p className="mb-3 text-sm text-slate-600">
        Creates a prospect client{lead.company ? ` “${lead.company}”` : ` “${lead.name}”`}, a contact{lead.email ? ` (${lead.email})` : ""} and an opportunity.
      </p>
      <form onSubmit={submit} className="grid gap-3 sm:grid-cols-4">
        <div className="sm:col-span-2"><Field label="Opportunity name"><input className={inputCls} value={name} onChange={(e) => setName(e.target.value)} /></Field></div>
        <Field label="Monthly ($)"><input className={inputCls} value={monthly} onChange={(e) => setMonthly(e.target.value)} inputMode="decimal" /></Field>
        <Field label="Term (months)"><input className={inputCls} type="number" min={1} max={120} value={term} onChange={(e) => setTerm(e.target.value)} /></Field>
        <Field label="Expected close"><input className={inputCls} type="date" value={close} onChange={(e) => setClose(e.target.value)} /></Field>
        <div className="sm:col-span-3"><Field label="Notes"><input className={inputCls} value={notes} onChange={(e) => setNotes(e.target.value)} /></Field></div>
        <div className="sm:col-span-4 space-y-2">
          {bad && <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{bad}</p>}
          <ErrorMsg error={convert.error} />
          <Button type="submit" disabled={convert.isPending}>Convert lead{parseMoney(monthly) ? ` (${money(parseMoney(monthly) ?? 0)}/mo)` : ""}</Button>
        </div>
      </form>
    </Card>
  );
}
