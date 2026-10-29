import { useQuery } from "@tanstack/react-query";
import { AgingRow, reportsApi } from "../../api";
import { money } from "../../money";
import { Card, ErrorMsg } from "../../ui";
import { dl, num } from "./SlaReport";

function Cells({ r }: { r: AgingRow }) {
  return (
    <>
      <td className={num}>{money(r.current_cents)}</td><td className={num}>{money(r.d1_30_cents)}</td><td className={num}>{money(r.d31_60_cents)}</td>
      <td className={num}>{money(r.d61_90_cents)}</td><td className={num}>{money(r.d90_plus_cents)}</td><td className={num + " font-medium"}>{money(r.total_open_cents)}</td>
      <td className={num}>{money(r.credit_cents)}</td><td className={num}>{r.overdue_invoice_count}/{r.open_invoice_count}</td>
    </>
  );
}

export default function AgingReport() {
  const q = useQuery({ queryKey: ["report", "aging"], queryFn: reportsApi.aging });
  const d = q.data;
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold tracking-tight">Receivables aging</h1>
      <Card title={d ? `Open balances as of ${d.as_of}` : "Open balances"} actions={<a className={dl} href={reportsApi.csv("aging")}>Download CSV</a>}>
        <ErrorMsg error={q.error} />
        <p className="mb-2 text-xs text-slate-500">Always as of today; there is no date range. Buckets are days past due. Overdue/open shows invoice counts.</p>
        {d && (
          <table className="w-full text-left text-sm">
            <thead className="border-b border-slate-200 text-slate-500"><tr><th className="p-1">Client</th><th className={num}>Current</th><th className={num}>1-30</th><th className={num}>31-60</th><th className={num}>61-90</th><th className={num}>90+</th><th className={num}>Total open</th><th className={num}>Credit</th><th className={num}>Overdue/open</th></tr></thead>
            <tbody>
              {d.rows.map((r) => <tr key={r.organization_id} className="border-b border-slate-100"><td className="p-1">{r.organization_name}</td><Cells r={r} /></tr>)}
              {d.rows.length === 0 && <tr><td colSpan={9} className="p-2 text-slate-500">Nothing is owed.</td></tr>}
            </tbody>
            {d.rows.length > 0 && <tfoot className="font-semibold"><tr><td className="p-1">Total</td><Cells r={d.totals} /></tr></tfoot>}
          </table>
        )}
      </Card>
    </div>
  );
}
