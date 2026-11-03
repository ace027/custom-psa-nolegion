import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { ProfitabilityTotals, hm, pctN, reportsApi } from "../../api";
import { can, useMe } from "../../auth";
import { money } from "../../money";
import { Card } from "../../ui";
import { TYPE_LABEL } from "../billing/Agreements";
import { QueryStatus, ReportTable, dl, num, useRange } from "./SlaReport";

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
  const [group, setGroup] = useState<"client" | "agreement">("client");
  const g = group === "agreement" ? "agreement" : undefined;
  const q = useQuery({ queryKey: ["report", "profitability", from, to, group], queryFn: () => reportsApi.profitability({ from, to, group: g }) });
  const d = q.data;
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold tracking-tight">Client profitability</h1>
      <Card title="Revenue against cost" actions={<a className={dl} href={reportsApi.csv("profitability", { from, to, group: g })}>Download CSV</a>}>
        {inputs}
        <div role="group" aria-label="Group by" className="my-2 flex gap-3 text-sm">
          {(["client", "agreement"] as const).map((v) => <label key={v}><input type="radio" name="profit-group" checked={group === v} onChange={() => setGroup(v)} /> {v === "client" ? "Client" : "Agreement"}</label>)}
        </div>
        <QueryStatus q={q} />
        <p className="my-2 text-xs text-slate-500">
          Revenue is finalized invoices excluding tax. Labour uses each technician's cost rate; time by someone with no rate counts as $0 and is listed under "No cost rate".
          {can(me, "user:manage")
            ? <> Set rates under <Link className="text-blue-700 hover:underline" to="/users">Users</Link> (Cost rate per hour).</>
            : " Ask an admin to set cost rates on the Users page."}
        </p>
        {d && (
          <ReportTable caption="Client profitability" busy={q.isFetching} minW="min-w-[60rem]">
            <thead className="border-b border-slate-200 text-slate-500"><tr><th scope="col" className="p-1">Client</th>{group === "agreement" && <><th scope="col">Agreement</th><th scope="col">Type</th></>}<th scope="col" className={num}>Revenue</th><th scope="col" className={num}>Labour</th><th scope="col" className={num}>Goods</th><th scope="col" className={num}>Expenses</th><th scope="col" className={num}>Cost</th><th scope="col" className={num}>Margin</th><th scope="col" className={num}>Margin %</th><th scope="col" className={num}>No cost rate</th><th scope="col" className={num}>Charges w/o cost</th></tr></thead>
            <tbody>
              {d.rows.map((r) => <tr key={`${r.organization_id}-${r.agreement_id ?? "none"}`} className="border-b border-slate-100"><th scope="row" className="p-1 font-normal">{r.organization_name}</th>{group === "agreement" && <><td>{r.agreement_name ?? "No agreement"}</td><td>{r.agreement_type ? (TYPE_LABEL[r.agreement_type as keyof typeof TYPE_LABEL] ?? r.agreement_type) : ""}</td></>}<Cells r={r} /></tr>)}
              {d.rows.length === 0 && <tr><td colSpan={12} className="p-2 text-slate-500">No revenue or cost in this range.</td></tr>}
            </tbody>
            {d.rows.length > 0 && <tfoot className="font-semibold"><tr><th scope="row" className="p-1">Total</th>{group === "agreement" && <td colSpan={2} />}<Cells r={d.totals} /></tr></tfoot>}
          </ReportTable>
        )}
      </Card>
    </div>
  );
}
