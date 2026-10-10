import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Receivables as ReceivablesData, api } from "../../api";
import { can, useMe } from "../../auth";
import { money } from "../../money";
import { ErrorMsg } from "../../ui";
import StatementActions from "./StatementActions";

export function useReceivables() {
  return useQuery({ queryKey: ["receivables"], queryFn: () => api<ReceivablesData>("/receivables"), refetchInterval: 60_000 });
}

export default function Receivables() {
  const { data: me } = useMe();
  const q = useReceivables();
  const d = q.data;
  const cell = (n: number, bad = false) => <td className={`text-right ${n === 0 ? "text-slate-300" : bad ? "text-red-700" : ""}`}>{n === 0 ? "–" : money(n)}</td>;
  return (
    <div className="space-y-4">
      <p className="text-sm text-slate-600">
        What clients owe, by how far past the <b>due date</b> it is. Balances are worked out from recorded payments and write-offs. "Credit" is money received but not yet applied to an invoice.
      </p>
      <ErrorMsg error={q.error} />
      {d && (
        <>
          <div className="flex flex-wrap gap-3 text-sm">
            <Stat label="Outstanding" value={money(d.totals.total_open_cents)} />
            <Stat label="Past due" value={money(d.totals.d1_30_cents + d.totals.d31_60_cents + d.totals.d61_90_cents + d.totals.d90_plus_cents)} warn={d.totals.overdue_invoice_count > 0} />
            <Stat label="Overdue invoices" value={String(d.totals.overdue_invoice_count)} warn={d.totals.overdue_invoice_count > 0} />
            <Stat label="Unapplied credit" value={money(d.totals.credit_cents)} />
          </div>
          <table className="w-full rounded-lg border border-slate-200 bg-surface text-left text-sm">
            <thead className="border-b border-slate-200 text-slate-500">
              <tr><th className="p-2">Client</th><th className="text-right">Current</th><th className="text-right">1–30</th><th className="text-right">31–60</th><th className="text-right">61–90</th><th className="text-right">90+</th><th className="text-right">Total owed</th><th className="text-right">Credit</th><th /></tr>
            </thead>
            <tbody>
              {d.rows.map((r) => (
                <tr key={r.organization_id} className="border-b border-slate-100">
                  <td className="p-2"><Link className="font-medium text-blue-700 hover:underline" to={`/billing/invoices?org=${r.organization_id}&pay=open`}>{r.organization_name}</Link><span className="ml-2 text-xs text-slate-500">{r.open_invoice_count} open{r.oldest_days_past_due > 0 ? `, oldest ${r.oldest_days_past_due}d late` : ""}</span></td>
                  {cell(r.current_cents)}{cell(r.d1_30_cents, true)}{cell(r.d31_60_cents, true)}{cell(r.d61_90_cents, true)}{cell(r.d90_plus_cents, true)}
                  <td className="text-right font-medium">{money(r.total_open_cents)}</td>
                  {cell(r.credit_cents)}
                  <td className="pl-4">{can(me, "payment:write") && <Link className="mr-3 text-blue-700 hover:underline" to={`/billing/payments?new=1&org=${r.organization_id}`}>Record payment</Link>}<StatementActions orgId={r.organization_id} /></td>
                </tr>
              ))}
              {d.rows.length === 0 && <tr><td colSpan={9} className="p-3 text-slate-500">Nothing outstanding.</td></tr>}
            </tbody>
            {d.rows.length > 0 && (
              <tfoot className="font-semibold">
                <tr className="border-t border-slate-300"><td className="p-2">Total</td>{cell(d.totals.current_cents)}{cell(d.totals.d1_30_cents, true)}{cell(d.totals.d31_60_cents, true)}{cell(d.totals.d61_90_cents, true)}{cell(d.totals.d90_plus_cents, true)}<td className="text-right">{money(d.totals.total_open_cents)}</td>{cell(d.totals.credit_cents)}<td /></tr>
              </tfoot>
            )}
          </table>
          <p className="text-xs text-slate-500">As of {d.as_of} (your business time zone).</p>
        </>
      )}
    </div>
  );
}

function Stat({ label, value, warn }: { label: string; value: string; warn?: boolean }) {
  return (
    <div className={`rounded-lg border px-4 py-2 ${warn ? "border-red-300 bg-red-50" : "border-slate-200 bg-surface"}`}>
      <div className="text-xl font-semibold">{value}</div>
      <div className="text-slate-500">{label}</div>
    </div>
  );
}
