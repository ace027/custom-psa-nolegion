import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Organization, Page, Quote, Survey, User, api } from "../../api";
import { can, useMe } from "../../auth";
import { money } from "../../money";
import { Button, Card, ErrorMsg, Field, fmt, inputCls } from "../../ui";

export const STATUS_STYLE: Record<string, string> = {
  draft: "bg-slate-100 text-slate-700",
  needs_approval: "bg-amber-100 text-amber-900",
  approved: "bg-blue-100 text-blue-800",
  sent: "bg-indigo-100 text-indigo-800",
  accepted: "bg-green-100 text-green-800",
  declined: "bg-red-100 text-red-800",
  cancelled: "bg-slate-100 text-slate-500",
};
export const Badge = ({ status, expired }: { status: string; expired?: boolean }) => (
  <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${STATUS_STYLE[status] ?? ""}`}>
    {status.replace("_", " ")}{expired ? " (expired)" : ""}
  </span>
);

export default function QuotesList() {
  const { data: me } = useMe();
  const canWrite = can(me, "quote:write");
  const quotes = useQuery({ queryKey: ["quotes"], queryFn: () => api<Quote[]>("/quotes") });
  const surveys = useQuery({ queryKey: ["surveys"], queryFn: () => api<Survey[]>("/surveys") });
  const needs = quotes.data?.filter((q) => q.status === "needs_approval").length ?? 0;
  // a completed survey with no open quote is waiting to be priced
  const openSurveyIds = new Set(quotes.data?.filter((q) => ["draft", "needs_approval", "approved", "sent"].includes(q.status)).map((q) => q.survey_id));
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold tracking-tight">Quotes</h1>
        <Link className="text-sm text-blue-700 hover:underline" to="/quotes/rates">Rate card</Link>
      </div>
      <ErrorMsg error={quotes.error ?? surveys.error} />
      {needs > 0 && <p className="rounded bg-amber-50 px-3 py-2 text-sm text-amber-900">{needs} quote{needs > 1 ? "s" : ""} waiting for approval.</p>}
      {canWrite && <NewSurvey />}
      <Card title="Site surveys">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-slate-200 text-slate-500"><tr><th className="py-1">Client</th><th>Status</th><th>Visit</th><th /></tr></thead>
          <tbody>
            {surveys.data?.map((s) => (
              <tr key={s.id} className="border-b border-slate-100">
                <td className="py-1">{s.organization_name}</td>
                <td><Badge status={s.status} /></td>
                <td>{fmt(s.scheduled_for)}</td>
                <td className="text-right">
                  <Link className="text-blue-700 hover:underline" to={`/quotes/surveys/${s.id}`}>
                    {s.status === "completed" ? (openSurveyIds.has(s.id) ? "view" : "price it") : "open"}
                  </Link>
                </td>
              </tr>
            ))}
            {surveys.data?.length === 0 && <tr><td colSpan={4} className="py-2 text-slate-500">No surveys yet.</td></tr>}
          </tbody>
        </table>
      </Card>
      <Card title="Quotes">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-slate-200 text-slate-500"><tr><th className="py-1">Quote</th><th>Client</th><th>Status</th><th className="text-right">Monthly</th><th>Valid until</th></tr></thead>
          <tbody>
            {quotes.data?.map((q) => (
              <tr key={q.id} className="border-b border-slate-100">
                <td className="py-1"><Link className="text-blue-700 hover:underline" to={`/quotes/${q.id}`}>{q.number}{q.version > 1 ? ` v${q.version}` : ""}</Link>{q.kind === "reprice" && <span className="ml-1 text-xs text-slate-500">reprice</span>}</td>
                <td>{q.organization_name}</td>
                <td><Badge status={q.status} expired={q.is_expired} /></td>
                <td className="text-right tabular-nums">{money(q.final_price_cents)}</td>
                <td>{q.valid_until ?? "—"}</td>
              </tr>
            ))}
            {quotes.data?.length === 0 && <tr><td colSpan={5} className="py-2 text-slate-500">No quotes yet. Schedule a survey, fill it in on site, then price it.</td></tr>}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

function NewSurvey() {
  const qc = useQueryClient();
  const nav = useNavigate();
  const orgs = useQuery({ queryKey: ["orgs", "", false], queryFn: () => api<Page<Organization>>("/organizations?limit=200&include_archived=false&q=") });
  const users = useQuery({ queryKey: ["users"], queryFn: () => api<User[]>("/users") });
  const [orgId, setOrgId] = useState("");
  const [newName, setNewName] = useState("");
  const [when, setWhen] = useState("");
  const [techId, setTechId] = useState("");
  const create = useMutation({
    mutationFn: async () => {
      let id = Number(orgId);
      if (!orgId) {
        const org = await api<Organization>("/organizations", { method: "POST", json: { name: newName, status: "prospect" } });
        id = org.id;
      }
      return api<Survey>(`/organizations/${id}/surveys`, { method: "POST", json: { scheduled_for: when ? new Date(when).toISOString() : null, tech_id: techId ? Number(techId) : null } });
    },
    onSuccess: (s) => { qc.invalidateQueries({ queryKey: ["surveys"] }); qc.invalidateQueries({ queryKey: ["orgs"] }); nav(`/quotes/surveys/${s.id}`); },
  });
  return (
    <Card title="Schedule a site survey">
      <form className="grid gap-3 sm:grid-cols-4" onSubmit={(e) => { e.preventDefault(); create.mutate(); }}>
        <Field label="Existing organization">
          <select className={inputCls} value={orgId} onChange={(e) => setOrgId(e.target.value)}>
            <option value="">New prospect…</option>
            {orgs.data?.items.map((o) => <option key={o.id} value={o.id}>{o.name}{o.status === "prospect" ? " (prospect)" : ""}</option>)}
          </select>
        </Field>
        {!orgId && <Field label="Prospect name"><input className={inputCls} required value={newName} onChange={(e) => setNewName(e.target.value)} /></Field>}
        <Field label="Visit date and time"><input className={inputCls} type="datetime-local" value={when} onChange={(e) => setWhen(e.target.value)} /></Field>
        <Field label="Tech">
          <select className={inputCls} value={techId} onChange={(e) => setTechId(e.target.value)}>
            <option value="">Unassigned</option>
            {users.data?.filter((u) => u.is_active && (u.role === "tech" || u.role === "admin")).map((u) => <option key={u.id} value={u.id}>{u.display_name}</option>)}
          </select>
        </Field>
        <div className="col-span-full space-y-2"><ErrorMsg error={create.error} /><Button type="submit" disabled={create.isPending}>Schedule survey</Button></div>
      </form>
    </Card>
  );
}
