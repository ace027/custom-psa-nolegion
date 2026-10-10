import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Run, RunDetail, api } from "../../api";
import { can, useMe } from "../../auth";
import { money } from "../../money";
import { Button, Card, ErrorMsg, Field, fmt, inputCls } from "../../ui";

const STATUS_STYLE: Record<string, string> = {
  draft: "bg-amber-100 text-amber-800",
  reviewed: "bg-blue-100 text-blue-800",
  finalized: "bg-green-100 text-green-800",
  cancelled: "bg-slate-100 text-slate-500",
  final: "bg-green-100 text-green-800",
  void: "bg-slate-100 text-slate-500",
};
export const StatusPill = ({ status }: { status: string }) => (
  <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${STATUS_STYLE[status] ?? ""}`}>{status}</span>
);

export function RunList() {
  const { data: me } = useMe();
  const nav = useNavigate();
  const qc = useQueryClient();
  const now = new Date();
  const [period, setPeriod] = useState(`${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`);
  const runs = useQuery({ queryKey: ["runs"], queryFn: () => api<Run[]>("/billing-runs") });
  const start = useMutation({
    mutationFn: () => api<RunDetail>("/billing-runs", { method: "POST", json: { period } }),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ["runs"] });
      nav(`/billing/runs/${r.id}`);
    },
  });
  return (
    <div className="space-y-4">
      <p className="text-sm text-slate-600">
        Each month: <b>start a run</b> (builds draft invoices from agreements, billable time and product charges), <b>review</b> the drafts and fix anything, then <b>finalize</b> to number and freeze the invoices.
      </p>
      {can(me, "billing:write") && (
        <form className="flex items-end gap-2" onSubmit={(e) => { e.preventDefault(); start.mutate(); }}>
          <Field label="Month (YYYY-MM)"><input className={inputCls} pattern="\d{4}-\d{2}" required value={period} onChange={(e) => setPeriod(e.target.value)} /></Field>
          <Button type="submit" disabled={start.isPending}>Start billing run</Button>
        </form>
      )}
      <ErrorMsg error={start.error ?? runs.error} />
      <table className="w-full rounded-lg border border-slate-200 bg-surface text-left text-sm">
        <thead className="border-b border-slate-200 text-slate-500"><tr><th className="p-2">Period</th><th>Status</th><th>Invoices</th><th>Total</th><th>Warnings</th></tr></thead>
        <tbody>
          {runs.data?.map((r) => (
            <tr key={r.id} className="border-b border-slate-100">
              <td className="p-2"><Link className="font-medium text-blue-700 hover:underline" to={`/billing/runs/${r.id}`}>{r.period_start.slice(0, 7)}</Link></td>
              <td><StatusPill status={r.status} /></td>
              <td>{r.invoice_count}</td>
              <td>{money(r.total_cents)}</td>
              <td>{r.warnings.length || ""}</td>
            </tr>
          ))}
          {runs.data?.length === 0 && <tr><td colSpan={5} className="p-3 text-slate-500">No runs yet.</td></tr>}
        </tbody>
      </table>
    </div>
  );
}

export function RunPage() {
  const id = Number(useParams().id);
  const { data: me } = useMe();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["run", id], queryFn: () => api<RunDetail>(`/billing-runs/${id}`) });
  const [date, setDate] = useState("");
  const refresh = () => qc.invalidateQueries();
  const act = useMutation({
    mutationFn: ({ path, json }: { path: string; json?: object }) => api<RunDetail>(`/billing-runs/${id}/${path}`, { method: "POST", json }),
    onSuccess: refresh,
  });
  const run = q.data;
  if (!run) return <ErrorMsg error={q.error ?? "Loading…"} />;
  const fin = can(me, "billing:finalize");
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-lg font-semibold">Billing run {run.period_start.slice(0, 7)}</h2>
        <StatusPill status={run.status} />
        <span className="text-sm text-slate-600">{run.invoice_count} invoices · {money(run.total_cents)}</span>
      </div>
      {run.warnings.length > 0 && (
        <Card title={`Warnings (${run.warnings.length}): read before finalizing`}>
          <ul className="list-disc pl-5 text-sm text-amber-800">{run.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>
        </Card>
      )}
      <ErrorMsg error={act.error} />
      {fin && (run.status === "draft" || run.status === "reviewed") && (
        <div className="flex flex-wrap items-end gap-3 rounded-lg border border-slate-200 bg-surface p-4">
          {run.status === "draft" && (
            <div className="text-sm">
              <p className="mb-2">Open each invoice, fix anything that looks wrong (quantities, mid-month changes, credits), then mark the run reviewed.</p>
              <Button onClick={() => act.mutate({ path: "review" })}>Mark reviewed</Button>
            </div>
          )}
          {run.status === "reviewed" && (
            <>
              <Field label="Invoice date (blank = today)"><input type="date" className={inputCls} value={date} onChange={(e) => setDate(e.target.value)} /></Field>
              <Button onClick={() => { if (window.confirm(`Finalize ${run.invoice_count} invoices totalling ${money(run.total_cents)}? Finalized invoices cannot be edited.`)) act.mutate({ path: "finalize", json: date ? { invoice_date: date } : {} }); }}>
                Finalize all invoices
              </Button>
            </>
          )}
          <Button variant="danger" onClick={() => { if (window.confirm("Cancel this run and discard its draft invoices?")) act.mutate({ path: "cancel" }); }}>Cancel run</Button>
        </div>
      )}
      <table className="w-full rounded-lg border border-slate-200 bg-surface text-left text-sm">
        <thead className="border-b border-slate-200 text-slate-500"><tr><th className="p-2">Client</th><th>Invoice</th><th>Status</th><th className="text-right">Subtotal</th><th className="text-right">Tax</th><th className="text-right">Total</th><th>Notes</th></tr></thead>
        <tbody>
          {run.invoices.map((i) => (
            <tr key={i.id} className="border-b border-slate-100">
              <td className="p-2">{i.organization_name}</td>
              <td><Link className="text-blue-700 hover:underline" to={`/billing/invoices/${i.id}`}>{i.number ?? "draft"}</Link></td>
              <td><StatusPill status={i.status} /></td>
              <td className="text-right">{money(i.subtotal_cents)}</td>
              <td className="text-right">{money(i.tax_cents)}</td>
              <td className="text-right font-medium">{money(i.total_cents)}</td>
              <td className="text-amber-800">{i.warnings.length ? `${i.warnings.length} warning(s)` : ""}{i.status === "void" && i.void_reason ? i.void_reason : ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="text-xs text-slate-500">Reviewed {fmt(run.reviewed_at)} · Finalized {fmt(run.finalized_at)}. Time logged after a run started is not included; use "Add unbilled" on a draft invoice, or it goes on next month's run.</p>
    </div>
  );
}
