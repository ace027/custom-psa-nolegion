import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { BillingMode, api, Organization, Page, PROJECT_STATUSES, PROJECT_STATUS_LABEL, ProjectInput, ProjectStatus, ProjectSummary, projectsApi } from "../api";
import { can, useMe } from "../auth";
import { money, parseMoney } from "../money";
import { Button, Card, ErrorMsg, Field, inputCls } from "../ui";

export const hours = (minutes: number) => `${(minutes / 60).toFixed(1)} h`;
export const MODE_LABEL: Record<BillingMode, string> = { fixed_fee: "Fixed fee", tm: "Time & materials" };

export function useOrgOptions() {
  return useQuery({
    queryKey: ["orgs-options"],
    queryFn: () => api<Page<Organization>>("/organizations?limit=200&include_archived=false&q="),
  });
}

function BudgetCells({ p }: { p: ProjectSummary }) {
  const b = useQuery({ queryKey: ["project-budget", p.id], queryFn: () => projectsApi.budget(p.id) });
  return (
    <>
      <td className="px-3 py-2">{b.data ? hours(b.data.actual_minutes) : "…"}</td>
      <td className="px-3 py-2">
        {b.data ? (b.data.remaining_cents === null ? "—" : money(b.data.remaining_cents)) : "…"}
        {b.data?.over_budget && <span className="ml-1 rounded-full bg-red-100 px-2 py-0.5 text-xs font-semibold text-red-800">Over budget</span>}
      </td>
    </>
  );
}

export default function Projects() {
  const { data: me } = useMe();
  const canWrite = can(me, "project:write");
  const [orgId, setOrgId] = useState("");
  const [status, setStatus] = useState<ProjectStatus | "">("");
  const orgs = useOrgOptions();
  const list = useQuery({
    queryKey: ["projects", orgId, status],
    queryFn: () => projectsApi.list({ organization_id: orgId ? Number(orgId) : undefined, status }),
  });
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold tracking-tight">Projects</h1>
      <div className="flex flex-wrap gap-3">
        <Field label="Client">
          <select className={inputCls} value={orgId} onChange={(e) => setOrgId(e.target.value)}>
            <option value="">All clients</option>
            {(orgs.data?.items ?? []).map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
          </select>
        </Field>
        <Field label="Status">
          <select className={inputCls} value={status} onChange={(e) => setStatus(e.target.value as ProjectStatus | "")}>
            <option value="">All statuses</option>
            {PROJECT_STATUSES.map((s) => <option key={s} value={s}>{PROJECT_STATUS_LABEL[s]}</option>)}
          </select>
        </Field>
      </div>
      <ErrorMsg error={list.error} />
      <Card title="All projects">
        {list.data && list.data.length === 0 ? (
          <p className="text-sm text-slate-500">No projects yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-slate-500">
                <tr>
                  <th className="px-3 py-2">Name</th><th className="px-3 py-2">Client</th><th className="px-3 py-2">Status</th>
                  <th className="px-3 py-2">Mode</th><th className="px-3 py-2">Budget / fee</th><th className="px-3 py-2">Actual</th><th className="px-3 py-2">Remaining</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {(list.data ?? []).map((p) => (
                  <tr key={p.id}>
                    <td className="px-3 py-2"><Link className="text-blue-700 hover:underline" to={`/projects/${p.id}`}>{p.name}</Link></td>
                    <td className="px-3 py-2">{p.organization_name}</td>
                    <td className="px-3 py-2">{PROJECT_STATUS_LABEL[p.status]}</td>
                    <td className="px-3 py-2">{p.billing_mode ? MODE_LABEL[p.billing_mode] : "—"}</td>
                    <td className="px-3 py-2">
                      {p.billing_mode === "fixed_fee" && p.fixed_fee_cents != null ? money(p.fixed_fee_cents) : p.billing_mode === "tm" && p.budget_cents != null ? money(p.budget_cents) : "—"}
                    </td>
                    <BudgetCells p={p} />
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
      {canWrite && <CreateProject canBill={can(me, "billing:write")} defaultOrg={orgId} />}
    </div>
  );
}

function CreateProject({ canBill, defaultOrg }: { canBill: boolean; defaultOrg: string }) {
  const nav = useNavigate();
  const qc = useQueryClient();
  const orgs = useOrgOptions();
  const [f, setF] = useState({ org: "", name: "", start: "", due: "", description: "", mode: "", fee: "", budget: "", taxable: false });
  const create = useMutation({
    mutationFn: () => {
      const json: ProjectInput = {
        organization_id: Number(f.org || defaultOrg),
        name: f.name,
        description: f.description || null,
        start_date: f.start || null,
        due_date: f.due || null,
      };
      if (canBill && f.mode) {
        json.billing_mode = f.mode as BillingMode;
        json.taxable = f.taxable;
        if (f.mode === "fixed_fee") {
          const c = parseMoney(f.fee);
          if (c === null || c <= 0) throw new Error("Enter the fixed fee, e.g. 2500.00");
          json.fixed_fee_cents = c;
        } else if (f.budget.trim()) {
          const c = parseMoney(f.budget);
          if (c === null || c <= 0) throw new Error("Enter a valid budget, e.g. 1000.00");
          json.budget_cents = c;
        }
      }
      return projectsApi.create(json);
    },
    onSuccess: (p) => {
      qc.invalidateQueries({ queryKey: ["projects"] });
      nav(`/projects/${p.id}`);
    },
  });
  return (
    <Card title="New project">
      <form
        className="grid gap-3 sm:grid-cols-3"
        onSubmit={(e) => {
          e.preventDefault();
          create.mutate();
        }}
      >
        <Field label="Project client">
          <select className={inputCls} required value={f.org || defaultOrg} onChange={(e) => setF({ ...f, org: e.target.value })}>
            <option value="">Choose…</option>
            {(orgs.data?.items ?? []).map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
          </select>
        </Field>
        <Field label="Project name"><input className={inputCls} required value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
        <Field label="Start date"><input className={inputCls} type="date" value={f.start} onChange={(e) => setF({ ...f, start: e.target.value })} /></Field>
        <Field label="Due date"><input className={inputCls} type="date" value={f.due} onChange={(e) => setF({ ...f, due: e.target.value })} /></Field>
        <div className="sm:col-span-2"><Field label="Description"><textarea className={inputCls} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></Field></div>
        {canBill && (
          <>
            <Field label="Billing mode">
              <select className={inputCls} value={f.mode} onChange={(e) => setF({ ...f, mode: e.target.value })}>
                <option value="">Decide later</option>
                <option value="fixed_fee">Fixed fee</option>
                <option value="tm">Time & materials</option>
              </select>
            </Field>
            {f.mode === "fixed_fee" && <Field label="Fixed fee ($)"><input className={inputCls} value={f.fee} onChange={(e) => setF({ ...f, fee: e.target.value })} /></Field>}
            {f.mode === "tm" && <Field label="Budget ($)"><input className={inputCls} value={f.budget} onChange={(e) => setF({ ...f, budget: e.target.value })} /></Field>}
            {f.mode && (
              <label className="flex items-end gap-1 text-sm"><input type="checkbox" checked={f.taxable} onChange={(e) => setF({ ...f, taxable: e.target.checked })} />Taxable</label>
            )}
          </>
        )}
        <div className="col-span-full space-y-2">
          <ErrorMsg error={create.error} />
          <Button type="submit" disabled={create.isPending}>Create project</Button>
        </div>
      </form>
    </Card>
  );
}
