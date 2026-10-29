import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { ProfitabilityTotals, hm, pctN, reportsApi } from "../../api";
import { can, useMe } from "../../auth";
import { money } from "../../money";
import { Card, ErrorMsg } from "../../ui";
import { dl, num, useRange } from "./SlaReport";

function Cells({ r }: { r: ProfitabilityTotals }) {
  return (
    <>
      <td className={num}>{money(r.revenue_cents)}</td><td className={num}>{money(r.labour_cost_cents)}</td><td className={num}>{money(r.goods_cost_cents)}</td>
      <td className={num}>{money(r.expense_cost_cents)}</td><td className={num}>{money(r.cost_cents)}</td><td className={num + " font-medium"}>{money(r.margin_cents)}</td>
      <td className={num}>{pctN(r.margin_bp)}</td>
      <td className={num + (r.minutes_without_cost_rate > 0 ? " text-amber-700" : "")}>{hm(r.minutes_without_cost_rate)}</td>
      <td className={num + (r.charges_without_cost > 0 ? " text-amber-700" : "")}>{r.charges_without_cost}</td>
    </>
  );
}

export default function ProfitabilityReport() {
  const { data: me } = useMe();
  const { from, to, inputs } = useRange();
  const q = useQuery({ queryKey: ["report", "profitability", from, to], queryFn: () => reportsApi.profitability({ from, to }) });
  const d = q.data;
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold tracking-tight">Client profitability</h1>
      <Card title="Revenue against cost" actions={<a className={dl} href={reportsApi.csv("profitability", { from, to })}>Download CSV</a>}>
        {inputs}
        <ErrorMsg error={q.error} />
        <p className="my-2 text-xs text-slate-500">
          Revenue is finalized invoices excluding tax. Labour uses each technician's cost rate; time by someone with no rate counts as $0 and is listed under "No cost rate".
          {can(me, "user:manage")
            ? <> Set rates under <Link className="text-blue-700 hover:underline" to="/users">Users</Link> (Cost rate per hour).</>
            : " Ask an admin to set cost rates on the Users page."}
        </p>
        {d && (
          <table className="w-full text-left text-sm">
            <thead className="border-b border-slate-200 text-slate-500"><tr><th className="p-1">Client</th><th className={num}>Revenue</th><th className={num}>Labour</th><th className={num}>Goods</th><th className={num}>Expenses</th><th className={num}>Cost</th><th className={num}>Margin</th><th className={num}>Margin %</th><th className={num}>No cost rate</th><th className={num}>Charges w/o cost</th></tr></thead>
            <tbody>
              {d.rows.map((r) => <tr key={r.organization_id} className="border-b border-slate-100"><td className="p-1">{r.organization_name}</td><Cells r={r} /></tr>)}
              {d.rows.length === 0 && <tr><td colSpan={10} className="p-2 text-slate-500">No revenue or cost in this range.</td></tr>}
            </tbody>
            {d.rows.length > 0 && <tfoot className="font-semibold"><tr><td className="p-1">Total</td><Cells r={d.totals} /></tr></tfoot>}
          </table>
        )}
      </Card>
    </div>
  );
}
