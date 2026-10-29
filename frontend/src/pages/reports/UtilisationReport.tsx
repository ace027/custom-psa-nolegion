import { useQuery } from "@tanstack/react-query";
import { hm, pctN, reportsApi } from "../../api";
import { Card, ErrorMsg } from "../../ui";
import { PctBar, dl, num, useRange } from "./SlaReport";

export default function UtilisationReport() {
  const { from, to, inputs } = useRange();
  const q = useQuery({ queryKey: ["report", "utilisation", from, to], queryFn: () => reportsApi.utilisation({ from, to }) });
  const d = q.data;
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold tracking-tight">Technician utilisation</h1>
      <Card title="Logged and billable time against capacity" actions={<a className={dl} href={reportsApi.csv("utilisation", { from, to })}>Download CSV</a>}>
        {inputs}
        <ErrorMsg error={q.error} />
        <p className="my-2 text-xs text-slate-500">n is capacity: working hours minus holidays and time off. Logged includes internal time; billable counts billable ticket time only.</p>
        {d && (
          <table className="w-full text-left text-sm">
            <thead className="border-b border-slate-200 text-slate-500"><tr><th className="p-1">Technician</th><th className={num}>Capacity</th><th className={num}>Logged</th><th className={num}>Billable</th><th className={num}>Utilisation (n)</th><th /><th className={num}>Billable % (n)</th></tr></thead>
            <tbody>
              {d.rows.map((r) => (
                <tr key={r.user_id} className="border-b border-slate-100">
                  <td className="p-1">{r.name}</td><td className={num}>{hm(r.capacity_minutes)}</td><td className={num}>{hm(r.logged_minutes)}</td><td className={num}>{hm(r.billable_minutes)}</td>
                  <td className={num}>{pctN(r.utilisation_bp, r.capacity_minutes)}</td><td className="pl-2"><PctBar bp={r.utilisation_bp} label={`Utilisation ${pctN(r.utilisation_bp)}`} /></td>
                  <td className={num}>{pctN(r.billable_bp, r.capacity_minutes)}</td>
                </tr>
              ))}
              {d.rows.length === 0 && <tr><td colSpan={7} className="p-2 text-slate-500">No technicians have capacity or time in this range.</td></tr>}
            </tbody>
            {d.rows.length > 0 && (
              <tfoot className="font-semibold"><tr><td className="p-1">Team</td><td className={num}>{hm(d.totals.capacity_minutes)}</td><td className={num}>{hm(d.totals.logged_minutes)}</td><td className={num}>{hm(d.totals.billable_minutes)}</td><td className={num}>{pctN(d.totals.utilisation_bp, d.totals.capacity_minutes)}</td><td /><td className={num}>{pctN(d.totals.billable_bp, d.totals.capacity_minutes)}</td></tr></tfoot>
            )}
          </table>
        )}
      </Card>
    </div>
  );
}
