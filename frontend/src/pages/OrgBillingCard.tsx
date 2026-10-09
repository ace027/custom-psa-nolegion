import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { OrgBilling, WorkTypeBilling, api } from "../api";
import { can, useMe } from "../auth";
import { money, parsePercent, parseMoney, percent } from "../money";
import { Button, Card, ErrorMsg, Field, inputCls } from "../ui";
import { useReceivables } from "./billing/Receivables";
import StatementActions from "./billing/StatementActions";

export default function OrgBillingCard({ orgId }: { orgId: number }) {
  const { data: me } = useMe();
  const canWrite = can(me, "billing:write");
  const qc = useQueryClient();
  const b = useQuery({ queryKey: ["org-billing", orgId], queryFn: () => api<OrgBilling>(`/organizations/${orgId}/billing`) });
  const wts = useQuery({ queryKey: ["wt-billing"], queryFn: () => api<WorkTypeBilling[]>("/billing/work-types") });
  const refresh = () => qc.invalidateQueries({ queryKey: ["org-billing", orgId] });
  const [terms, setTerms] = useState<string | null>(null);
  const [tax, setTax] = useState<string | null>(null);
  const save = useMutation({
    mutationFn: () => {
      const bp = tax === null ? undefined : parsePercent(tax);
      if (tax !== null && bp === null) throw new Error("Tax rate must look like 8.25");
      return api(`/organizations/${orgId}/billing`, { method: "PATCH", json: { ...(terms !== null ? { payment_terms_days: Number(terms) } : {}), ...(bp !== undefined ? { tax_rate_bp: bp } : {}) } });
    },
    onSuccess: () => { setTerms(null); setTax(null); refresh(); },
  });
  const remind = useMutation({
    mutationFn: (do_not_remind: boolean) => api(`/organizations/${orgId}/billing`, { method: "PATCH", json: { do_not_remind } }),
    onSuccess: refresh,
  });
  const lateFees = useMutation({
    mutationFn: (late_fees_enabled: boolean) => api(`/organizations/${orgId}/billing`, { method: "PATCH", json: { late_fees_enabled } }),
    onSuccess: refresh,
  });
  const setRate = useMutation({
    mutationFn: ({ wt, text }: { wt: number; text: string }) => {
      if (text.trim() === "") return api(`/organizations/${orgId}/billing/rates/${wt}`, { method: "DELETE" });
      const c = parseMoney(text);
      if (c === null) throw new Error("Enter a valid rate");
      return api(`/organizations/${orgId}/billing/rates/${wt}`, { method: "PUT", json: { rate_cents: c } });
    },
    onSuccess: refresh,
  });
  const rec = useReceivables();
  const acct = rec.data?.rows.find((r) => r.organization_id === orgId);
  if (!b.data) return null;
  const overrides = new Map(b.data.rates.map((r) => [r.work_type_id, r.rate_cents]));
  return (
    <Card title="Billing">
      <p className="mb-3 text-sm">
        Account: <b>{money(acct?.total_open_cents ?? 0)}</b> outstanding
        {acct && acct.overdue_invoice_count > 0 && <span className="text-red-700"> ({acct.overdue_invoice_count} overdue, oldest {acct.oldest_days_past_due} days)</span>}
        {acct && acct.credit_cents > 0 && <span> · <b>{money(acct.credit_cents)}</b> unapplied credit</span>}
      </p>
      <div className="mb-3 flex flex-wrap items-center gap-4 text-sm">
        <StatementActions orgId={orgId} />
        <label className="flex items-center gap-1">
          <input type="checkbox" disabled={!canWrite} checked={b.data.do_not_remind} onChange={(e) => remind.mutate(e.target.checked)} />
          Do not send payment reminders to this client
        </label>
        <label className="flex items-center gap-1">
          <input type="checkbox" disabled={!canWrite} checked={b.data.late_fees_enabled} onChange={(e) => lateFees.mutate(e.target.checked)} />
          Charge late fees to this client (when approved on Billing → Late fees)
        </label>
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        <Field label="Payment terms (days)"><input className={inputCls} type="number" min={0} max={365} disabled={!canWrite} value={terms ?? b.data.payment_terms_days} onChange={(e) => setTerms(e.target.value)} /></Field>
        <Field label="Sales tax rate (%)"><input className={inputCls} disabled={!canWrite} value={tax ?? percent(b.data.tax_rate_bp).replace("%", "")} onChange={(e) => setTax(e.target.value)} /></Field>
        <div className="flex items-end">{canWrite && (terms !== null || tax !== null) && <Button onClick={() => save.mutate()}>Save</Button>}</div>
      </div>
      <p className="mt-3 text-sm font-medium">Hourly rate overrides (blank = use the default rate)</p>
      <table className="text-sm">
        <tbody>
          {wts.data?.filter((w) => !w.archived_at).map((w) => (
            <tr key={w.id}>
              <td className="pr-4">{w.name}</td>
              <td className="pr-2 text-slate-500">default {w.rate_cents === null ? "not set" : money(w.rate_cents)}</td>
              <td><input aria-label={`${w.name} override`} className={inputCls + " w-28"} disabled={!canWrite} defaultValue={overrides.has(w.id) ? money(overrides.get(w.id)!).replace("$", "") : ""} onBlur={(e) => { const cur = overrides.has(w.id) ? money(overrides.get(w.id)!).replace("$", "") : ""; if (e.target.value !== cur) setRate.mutate({ wt: w.id, text: e.target.value }); }} /></td>
            </tr>
          ))}
        </tbody>
      </table>
      <ErrorMsg error={save.error ?? setRate.error ?? remind.error ?? lateFees.error} />
    </Card>
  );
}
