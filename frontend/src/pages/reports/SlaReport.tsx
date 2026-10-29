import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { SlaClock, SlaGroup, hm, pctN, reportsApi, thisMonth } from "../../api";
import { Card, ErrorMsg, Field, inputCls } from "../../ui";

export const dl = "text-sm text-blue-700 hover:underline";
export const num = "text-right tabular-nums";

/** Start/end inputs, defaulting to this month. Shared by the range-based reports. */
export function useRange() {
  const [range, setRange] = useState(thisMonth);
  const inputs = (
    <div className="flex flex-wrap gap-3">
      <Field label="From"><input className={inputCls} type="date" value={range.from} onChange={(e) => setRange({ ...range, from: e.target.value })} /></Field>
      <Field label="To"><input className={inputCls} type="date" value={range.to} onChange={(e) => setRange({ ...range, to: e.target.value })} /></Field>
    </div>
  );
  return { from: range.from, to: range.to, inputs };
}

/** A plain CSS width bar for a basis-point percentage (empty when null). */
export function PctBar({ bp, label }: { bp: number | null; label: string }) {
  const width = bp === null ? 0 : Math.min(100, Math.max(0, bp / 100));
  return (
    <span role="img" aria-label={label} className="block h-2 w-24 rounded bg-slate-200">
      <span className="block h-2 rounded bg-blue-500" style={{ width: `${width}%` }} />
    </span>
  );
}

function ClockCells({ c }: { c: SlaClock }) {
  return (
    <>
      <td className={num}>{pctN(c.met_bp, c.met + c.breached)}</td>
      <td className="pl-2"><PctBar bp={c.met_bp} label={`Met ${pctN(c.met_bp)}`} /></td>
      <td className={num}>{c.breached}</td>
      <td className={num}>{c.pending}</td>
      <td className={num}>{hm(c.p50_minutes)}</td>
      <td className={num}>{hm(c.p90_minutes)}</td>
    </>
  );
}

const GROUPS: { value: SlaGroup; label: string }[] = [
  { value: "priority", label: "Priority" },
  { value: "organization", label: "Client" },
  { value: "assignee", label: "Assignee" },
];

export default function SlaReport() {
  const { from, to, inputs } = useRange();
  const [group, setGroup] = useState<SlaGroup>("priority");
  const q = useQuery({ queryKey: ["report", "sla", from, to, group], queryFn: () => reportsApi.sla({ from, to, group }) });
  const d = q.data;
  const head = (
    <>
      <th className={num}>Met % (n)</th><th /><th className={num}>Breached</th><th className={num}>Pending</th><th className={num}>p50</th><th className={num}>p90</th>
    </>
  );
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold tracking-tight">SLA performance</h1>
      <Card title="Tickets created in range" actions={<a className={dl} href={reportsApi.csv("sla", { from, to, group })}>Download CSV</a>}>
        <div className="flex flex-wrap items-end gap-3">
          {inputs}
          <Field label="Group by">
            <select className={inputCls} value={group} onChange={(e) => setGroup(e.target.value as SlaGroup)}>
              {GROUPS.map((g) => <option key={g.value} value={g.value}>{g.label}</option>)}
            </select>
          </Field>
        </div>
        <ErrorMsg error={q.error} />
        <p className="my-2 text-xs text-slate-500">Percentages count met and breached tickets only (n); pending tickets and tickets with no SLA are excluded. Durations are business time, p50 and p90.</p>
        {d && (
          <table className="w-full text-left text-sm">
            <thead className="border-b border-slate-200 text-slate-500">
              <tr><th rowSpan={2} className="p-1">{GROUPS.find((g) => g.value === d.group)?.label}</th><th rowSpan={2} className={num}>Tickets</th><th colSpan={6} className="text-center">First response</th><th colSpan={6} className="text-center">Resolution</th></tr>
              <tr>{head}{head}</tr>
            </thead>
            <tbody>
              {d.rows.map((r) => (
                <tr key={r.key ?? r.label} className="border-b border-slate-100"><td className="p-1">{r.label}</td><td className={num}>{r.n}</td><ClockCells c={r.first_response} /><ClockCells c={r.resolution} /></tr>
              ))}
              {d.rows.length === 0 && <tr><td colSpan={14} className="p-2 text-slate-500">No tickets were created in this range.</td></tr>}
            </tbody>
            {d.rows.length > 0 && <tfoot className="font-semibold"><tr><td className="p-1">Total</td><td className={num}>{d.totals.n}</td><ClockCells c={d.totals.first_response} /><ClockCells c={d.totals.resolution} /></tr></tfoot>}
          </table>
        )}
      </Card>
    </div>
  );
}
