import { useQuery } from "@tanstack/react-query";
import { hm, pctN, reportsApi } from "../../api";
import { Card } from "../../ui";
import { PctBar, QueryStatus, ReportTable, dl, num, useRange } from "./SlaReport";

export default function UtilisationReport() {
  const { from, to, inputs } = useRange();
  const q = useQuery({ queryKey: ["report", "utilisation", from, to], queryFn: () => reportsApi.utilisation({ from, to }) });
  const d = q.data;
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold tracking-tight">Technician utilisation</h1>
      <Card title="Logged and billable time against capacity" actions={<a className={dl} href={reportsApi.csv("utilisation", { from, to })}>Download CSV</a>}>
        {inputs}
        <QueryStatus q={q} />
        <p className="my-2 text-xs text-slate-500">n is capacity: working hours minus holidays and time off. Logged includes internal time; billable counts billable ticket time only.</p>
        {d && (
          <ReportTable caption="Technician utilisation" busy={q.isFetching} minW="min-w-[48rem]">
            <thead className="border-b border-slate-200 text-slate-500"><tr><th scope="col" className="p-1">Technician</th><th scope="col" className={num}>Capacity</th><th scope="col" className={num}>Logged</th><th scope="col" className={num}>Billable</th><th scope="col" className={num} title="Not counted in utilisation %">Automation</th><th scope="col" className={num}>Utilisation (n)</th><th scope="col"><span className="sr-only">Utilisation bar</span></th><th scope="col" className={num}>Billable % (n)</th></tr></thead>
            <tbody>
              {d.rows.map((r) => (
                <tr key={r.user_id} className="border-b border-slate-100">
                  <th scope="row" className="p-1 font-normal">{r.name}</th><td className={num}>{hm(r.capacity_minutes)}</td><td className={num}>{hm(r.logged_minutes)}</td><td className={num}>{hm(r.billable_minutes)}</td><td className={num}>{hm(r.automation_minutes)}</td>
                  <td className={num}>{pctN(r.utilisation_bp, r.capacity_minutes)}</td><td className="pl-2"><PctBar bp={r.utilisation_bp} /></td>
                  <td className={num}>{pctN(r.billable_bp, r.capacity_minutes)}</td>
                </tr>
              ))}
              {d.rows.length === 0 && <tr><td colSpan={8} className="p-2 text-slate-500">No technicians have capacity or time in this range.</td></tr>}
            </tbody>
            {d.rows.length > 0 && (
              <tfoot className="font-semibold"><tr><th scope="row" className="p-1">Team</th><td className={num}>{hm(d.totals.capacity_minutes)}</td><td className={num}>{hm(d.totals.logged_minutes)}</td><td className={num}>{hm(d.totals.billable_minutes)}</td><td className={num}>{hm(d.rows.reduce((s, r) => s + r.automation_minutes, 0))}</td><td className={num}>{pctN(d.totals.utilisation_bp, d.totals.capacity_minutes)}</td><td /><td className={num}>{pctN(d.totals.billable_bp, d.totals.capacity_minutes)}</td></tr></tfoot>
            )}
          </ReportTable>
        )}
      </Card>
    </div>
  );
}
