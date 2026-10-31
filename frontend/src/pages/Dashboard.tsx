import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { CsatSummary, Dashboard as DashboardData, api, hm, pctN, reportsApi } from "../api";
import { can, useMe } from "../auth";
import { money } from "../money";
import { Card, ErrorMsg } from "../ui";
import { daysLeft, useOpenRenewals } from "./crm/Renewals";
import { QueryStatus } from "./reports/SlaReport";
import TicketTable from "./TicketTable";
import { clientRoute } from "../clientScope";

export default function Dashboard() {
  const q = useQuery({ queryKey: ["dashboard"], queryFn: () => api<DashboardData>("/dashboard"), refetchInterval: 60_000 });
  const d = q.data;
  const { data: me } = useMe();
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold tracking-tight">Dashboard</h1>
      <ErrorMsg error={q.error} />
      <MyWeek />
      {can(me, "report:read") && <Business />}
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
          {can(me, "crm:read") && <RenewalsCard />}
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

function RenewalsCard() {
  const q = useOpenRenewals();
  const rows = (q.data ?? []).slice(0, 5);
  return (
    <Card title="Renewals due" actions={<Link className="text-sm text-blue-700 hover:underline" to="/crm/renewals">All renewals</Link>}>
      <ErrorMsg error={q.error} />
      {q.data && rows.length === 0 && <p className="text-sm text-slate-500">No renewals are due.</p>}
      <ul className="divide-y divide-slate-100 text-sm">
        {rows.map((r) => (
          <li key={r.id} className="flex flex-wrap justify-between gap-2 py-1.5">
            <span><Link className="text-blue-700 hover:underline" to={clientRoute(r.organization_id)}>{r.organization_name}</Link> · {r.agreement_name}</span>
            <span className="text-slate-600">{r.due_on} ({daysLeft(r.due_on)} days)</span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function Tile({ label, value, to, warn }: { label: string; value: string; to?: string; warn?: boolean }) {
  const body = (
    <>
      <div className="text-xl font-semibold tabular-nums">{value}</div>
      <div className="text-slate-500">{label}</div>
    </>
  );
  const cls = `block rounded-xl border px-4 py-3 shadow-card ${warn ? "border-amber-300 bg-amber-50" : "border-slate-200 bg-surface"}`;
  return to ? <Link to={to} className={`${cls} hover:border-blue-400`}>{body}</Link> : <div className={cls}>{body}</div>;
}

function MyWeek() {
  const q = useQuery({ queryKey: ["dashboard-me"], queryFn: reportsApi.myDashboard, refetchInterval: 60_000 });
  const d = q.data;
  return (
    <Card title="My week">
      <QueryStatus q={q} />
      {d && (
        <div aria-busy={q.isFetching} className={`grid grid-cols-2 gap-3 text-sm sm:grid-cols-3 lg:grid-cols-4 ${q.isFetching ? "opacity-60" : ""}`}>
          <Tile label="My open tickets" value={String(d.open_tickets)} to="/tickets" />
          <Tile label="My SLA at risk" value={String(d.sla_at_risk)} warn={d.sla_at_risk > 0} />
          <Tile label="My SLA breached" value={String(d.sla_breached)} warn={d.sla_breached > 0} />
          <Tile label="Appointments today" value={String(d.appointments_today)} to="/dispatch" />
          <Tile label="Logged this week" value={hm(d.week.logged_minutes)} to="/timesheet" />
          <Tile label="Billable this week" value={hm(d.week.billable_minutes)} />
          <Tile label="Capacity this week" value={hm(d.week.capacity_minutes)} />
          <Tile label="My utilisation" value={pctN(d.week.utilisation_bp)} />
        </div>
      )}
    </Card>
  );
}

function Business() {
  const q = useQuery({ queryKey: ["dashboard-business"], queryFn: reportsApi.managerDashboard, refetchInterval: 60_000 });
  const d = q.data;
  return (
    <Card title="Business">
      <QueryStatus q={q} />
      {d && (
        <div aria-busy={q.isFetching} className={`space-y-3 text-sm ${q.isFetching ? "opacity-60" : ""}`}>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
            <Tile label="Revenue month to date" value={money(d.revenue_mtd_cents)} to="/billing/reports" />
            <Tile label="Margin month to date" value={money(d.margin_mtd_cents)} to="/reports/profitability" />
            <Tile label="Margin % month to date" value={pctN(d.margin_mtd_bp)} to="/reports/profitability" />
            <Tile label="Receivables (AR) total" value={money(d.ar_total_cents)} to="/reports/aging" />
            <Tile label="Unbilled work" value={money(d.unbilled_cents)} to="/billing/reports" />
            <Tile label="SLA first response met, 30 days" value={pctN(d.sla_30d.first_response_met_bp, d.sla_30d.n)} to="/reports/sla" />
            <Tile label="SLA resolution met, 30 days" value={pctN(d.sla_30d.resolution_met_bp, d.sla_30d.n)} to="/reports/sla" />
            <Tile label="Team utilisation last week" value={pctN(d.team_utilisation_last_week_bp)} to="/reports/utilisation" />
          </div>
          <div>
            <h3 className="mb-1 font-medium text-slate-700">Receivables by days past due</h3>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
              <Tile label="Current" value={money(d.ar_buckets.current_cents)} to="/reports/aging" />
              <Tile label="1-30" value={money(d.ar_buckets.d1_30_cents)} to="/reports/aging" />
              <Tile label="31-60" value={money(d.ar_buckets.d31_60_cents)} to="/reports/aging" />
              <Tile label="61-90" value={money(d.ar_buckets.d61_90_cents)} to="/reports/aging" />
              <Tile label="90+" value={money(d.ar_buckets.d90_plus_cents)} to="/reports/aging" warn={d.ar_buckets.d90_plus_cents > 0} />
            </div>
          </div>
        </div>
      )}
    </Card>
  );
}
