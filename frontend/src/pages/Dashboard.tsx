import { useQuery } from "@tanstack/react-query";
import { CsatSummary, Dashboard as DashboardData, api } from "../api";
import { Card, ErrorMsg } from "../ui";
import TicketTable from "./TicketTable";

export default function Dashboard() {
  const q = useQuery({ queryKey: ["dashboard"], queryFn: () => api<DashboardData>("/dashboard"), refetchInterval: 60_000 });
  const d = q.data;
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold tracking-tight">Dashboard</h1>
      <ErrorMsg error={q.error} />
      {d && (
        <>
          <div className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-3 lg:grid-cols-5">
            <Stat label="Open" value={d.counts.open} />
            <Stat label="Mine" value={d.counts.mine} />
            <Stat label="Unassigned" value={d.counts.unassigned} />
            <Stat label="SLA at risk" value={d.counts.sla_at_risk} warn={d.counts.sla_at_risk > 0} />
            <Stat label="Needs triage" value={d.counts.needs_triage} warn={d.counts.needs_triage > 0} />
          </div>
          <CsatCard />
          <Card title="SLA at risk or breached">
            <TicketTable tickets={d.sla_at_risk} empty="Nothing at risk." />
          </Card>
          <Card title="My open tickets">
            <TicketTable tickets={d.my_open} empty="Nothing assigned to you." />
          </Card>
          <Card title="Unassigned">
            <TicketTable tickets={d.unassigned} empty="Everything is assigned." />
          </Card>
        </>
      )}
    </div>
  );
}

function Stat({ label, value, warn }: { label: string; value: number; warn?: boolean }) {
  return (
    <div className={`rounded-xl border px-4 py-3 shadow-card ${warn ? "border-amber-300 bg-amber-50" : "border-slate-200 bg-surface"}`}>
      <div className="text-2xl font-semibold">{value}</div>
      <div className="text-slate-500">{label}</div>
    </div>
  );
}

function CsatCard() {
  const q = useQuery({ queryKey: ["csat-summary"], queryFn: () => api<CsatSummary>("/csat/summary?days=90") });
  const s = q.data;
  if (!s || s.requested === 0) return null;
  return (
    <Card title="Customer satisfaction (last 90 days)">
      <p className="text-sm">
        <b className="text-2xl">{s.average === null ? "–" : s.average.toFixed(2)}</b>
        <span className="text-slate-500"> / 5 average · {s.responses} of {s.requested} surveys answered</span>
      </p>
      <ul className="mt-2 flex gap-4 text-sm text-slate-600">
        {[5, 4, 3, 2, 1].map((n) => <li key={n}>{n}★ {s.distribution[String(n)] ?? 0}</li>)}
      </ul>
    </Card>
  );
}
