import { useQuery } from "@tanstack/react-query";
import { Dashboard as DashboardData, api } from "../api";
import { Card, ErrorMsg } from "../ui";
import TicketTable from "./TicketTable";

export default function Dashboard() {
  const q = useQuery({ queryKey: ["dashboard"], queryFn: () => api<DashboardData>("/dashboard"), refetchInterval: 60_000 });
  const d = q.data;
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Dashboard</h1>
      <ErrorMsg error={q.error} />
      {d && (
        <>
          <div className="flex flex-wrap gap-3 text-sm">
            <Stat label="Open" value={d.counts.open} />
            <Stat label="Mine" value={d.counts.mine} />
            <Stat label="Unassigned" value={d.counts.unassigned} />
            <Stat label="SLA at risk" value={d.counts.sla_at_risk} warn={d.counts.sla_at_risk > 0} />
            <Stat label="Needs triage" value={d.counts.needs_triage} warn={d.counts.needs_triage > 0} />
          </div>
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
    <div className={`rounded-lg border px-4 py-2 ${warn ? "border-amber-300 bg-amber-50" : "border-slate-200 bg-white"}`}>
      <div className="text-2xl font-semibold">{value}</div>
      <div className="text-slate-500">{label}</div>
    </div>
  );
}
