import { useQuery } from "@tanstack/react-query";
import { ForecastBucket, crmApi } from "../../api";
import { money } from "../../money";
import { ErrorMsg, StatTile } from "../../ui";

export default function Forecast() {
  const q = useQuery({ queryKey: ["crm", "forecast"], queryFn: crmApi.forecast });
  const f = q.data;
  const row = (b: ForecastBucket, strong = false) => (
    <tr key={b.key} className={`border-b border-slate-100 ${strong ? "font-semibold" : ""}`}>
      <td className="py-1.5">{b.label}</td>
      <td className="text-right tabular-nums">{b.count}</td>
      <td className="text-right tabular-nums">{money(b.monthly_cents)}</td>
      <td className="text-right tabular-nums">{money(b.weighted_monthly_cents)}</td>
      <td className="text-right tabular-nums">{money(b.contract_value_cents)}</td>
    </tr>
  );
  return (
    <div className="space-y-4">
      <ErrorMsg error={q.error} />
      {f && (
        <>
          <div className="grid grid-cols-2 gap-3 sm:max-w-xl">
            <StatTile label="Won this month (monthly)" value={money(f.won_this_month.monthly_cents)} />
            <StatTile label="Won this quarter (monthly)" value={money(f.won_this_quarter.monthly_cents)} />
          </div>
          <p className="text-xs text-slate-500">
            Won this month: {f.won_this_month.count} deal(s), {money(f.won_this_month.contract_value_cents)} contract value.
            This quarter: {f.won_this_quarter.count} deal(s), {money(f.won_this_quarter.contract_value_cents)}.
          </p>
          {f.buckets.length === 0 ? (
            <p className="text-sm text-slate-500">No open opportunities to forecast.</p>
          ) : (
            <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <caption className="sr-only">Forecast by expected close month</caption>
              <thead>
                <tr className="border-b border-slate-200 text-left text-slate-500">
                  <th scope="col" className="py-1.5">Close month</th>
                  <th scope="col" className="text-right">Opportunities</th>
                  <th scope="col" className="text-right">Monthly</th>
                  <th scope="col" className="text-right">Weighted monthly</th>
                  <th scope="col" className="text-right">Contract value</th>
                </tr>
              </thead>
              <tbody>
                {f.buckets.map((b) => row(b))}
                {row({ ...f.total, label: "Total" }, true)}
              </tbody>
            </table>
            </div>
          )}
          <p className="text-xs text-slate-500">Estimates only. Weighted monthly is monthly times the stage probability; nothing here is billed.</p>
        </>
      )}
    </div>
  );
}
