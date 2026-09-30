import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { RecurringReport, RevenueReport, UnbilledReport, api } from "../../api";
import { money } from "../../money";
import { Card, ErrorMsg, Field, inputCls } from "../../ui";

const dl = "text-sm text-blue-700 hover:underline";
const num = "text-right tabular-nums";

export default function Reports() {
  return (
    <div className="space-y-4">
      <p className="text-sm text-slate-600">
        Figures come from finalized invoices, so they match what clients were billed. Downloads are recorded in the audit log.
      </p>
      <RevenueCard />
      <UnbilledCard />
      <RecurringCard />
      <InvoiceExport />
    </div>
  );
}

function useRange() {
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const qs = new URLSearchParams({ ...(from ? { from } : {}), ...(to ? { to } : {}) }).toString();
  const inputs = (
    <div className="flex flex-wrap gap-3">
      <Field label="From"><input className={inputCls} type="date" value={from} onChange={(e) => setFrom(e.target.value)} /></Field>
      <Field label="To"><input className={inputCls} type="date" value={to} onChange={(e) => setTo(e.target.value)} /></Field>
    </div>
  );
  return { qs: qs ? `?${qs}` : "", inputs };
}

function RevenueCard() {
  const { qs, inputs } = useRange();
  const q = useQuery({ queryKey: ["report", "revenue", qs], queryFn: () => api<RevenueReport>(`/reports/revenue${qs}`) });
  const d = q.data;
  return (
    <Card title="Revenue" actions={<a className={dl} href={`/api/reports/revenue.csv${qs}`}>Download CSV</a>}>
      {inputs}
      <ErrorMsg error={q.error} />
      {d && (
        <>
          <p className="my-2 text-xs text-slate-500">Finalized, non-void invoices by invoice date, {d.start} to {d.end}. Excludes tax from the kind columns; Total includes it.</p>
          <table className="w-full text-left text-sm">
            <thead className="border-b border-slate-200 text-slate-500"><tr><th className="p-1">Client</th><th className={num}>Invoices</th><th className={num}>Time</th><th className={num}>Products</th><th className={num}>Agreements</th><th className={num}>Other</th><th className={num}>Tax</th><th className={num}>Total</th></tr></thead>
            <tbody>
              {d.clients.map((c) => (
                <tr key={c.organization_id} className="border-b border-slate-100"><td className="p-1">{c.organization_name}</td><td className={num}>{c.invoices}</td><td className={num}>{money(c.time_cents)}</td><td className={num}>{money(c.product_cents)}</td><td className={num}>{money(c.agreement_cents)}</td><td className={num}>{money(c.manual_cents)}</td><td className={num}>{money(c.tax_cents)}</td><td className={num + " font-medium"}>{money(c.total_cents)}</td></tr>
              ))}
              {d.clients.length === 0 && <tr><td colSpan={8} className="p-2 text-slate-500">No invoices in this range.</td></tr>}
            </tbody>
            {d.clients.length > 0 && <tfoot className="font-semibold"><tr><td className="p-1">Total</td><td className={num}>{d.totals.invoices}</td><td className={num}>{money(d.totals.time_cents)}</td><td className={num}>{money(d.totals.product_cents)}</td><td className={num}>{money(d.totals.agreement_cents)}</td><td className={num}>{money(d.totals.manual_cents)}</td><td className={num}>{money(d.totals.tax_cents)}</td><td className={num}>{money(d.totals.total_cents)}</td></tr></tfoot>}
          </table>
          <h3 className="mt-4 text-sm font-medium">By month</h3>
          <Bars rows={d.months.map((m) => ({ label: m.month.slice(0, 7), cents: m.total_cents }))} />
        </>
      )}
    </Card>
  );
}

/** A plain horizontal bar list: readable without a chart library, with the numbers alongside. */
function Bars({ rows }: { rows: { label: string; cents: number }[] }) {
  const max = Math.max(1, ...rows.map((r) => r.cents));
  return (
    <ul className="mt-1 space-y-0.5 text-sm">
      {rows.map((r) => (
        <li key={r.label} className="flex items-center gap-2">
          <span className="w-16 text-slate-500">{r.label}</span>
          <span className="h-3 rounded bg-blue-500" style={{ width: `${Math.max(0, (r.cents / max) * 60)}%` }} />
          <span className="tabular-nums">{money(r.cents)}</span>
        </li>
      ))}
    </ul>
  );
}

function UnbilledCard() {
  const q = useQuery({ queryKey: ["report", "unbilled"], queryFn: () => api<UnbilledReport>("/reports/unbilled") });
  const d = q.data;
  return (
    <Card title="Unbilled work" actions={<a className={dl} href="/api/reports/unbilled.csv">Download CSV</a>}>
      <ErrorMsg error={q.error} />
      {d && (
        <>
          <p className="mb-2 text-xs text-slate-500">Billable time and one-off charges not yet on an invoice, up to {d.through}. Time is priced at today's rates before tax; time with no rate is shown as hours, not dollars.</p>
          <table className="w-full text-left text-sm">
            <thead className="border-b border-slate-200 text-slate-500"><tr><th className="p-1">Client</th><th className={num}>Hours</th><th className={num}>Time</th><th className={num}>Charges</th><th className={num}>Total</th><th>Oldest</th></tr></thead>
            <tbody>
              {d.rows.map((r) => (
                <tr key={r.organization_id} className="border-b border-slate-100"><td className="p-1">{r.organization_name}</td><td className={num}>{(r.billable_minutes / 60).toFixed(2)}{r.unpriced_minutes > 0 && <span className="ml-1 text-amber-700" title="Hours with no hourly rate set">({(r.unpriced_minutes / 60).toFixed(2)} unpriced)</span>}</td><td className={num}>{money(r.time_value_cents)}</td><td className={num}>{money(r.charges_cents)}</td><td className={num + " font-medium"}>{money(r.total_cents)}</td><td className="pl-3 text-slate-500">{r.oldest_work_date}</td></tr>
              ))}
              {d.rows.length === 0 && <tr><td colSpan={6} className="p-2 text-slate-500">Nothing unbilled.</td></tr>}
            </tbody>
            {d.rows.length > 0 && <tfoot className="font-semibold"><tr><td className="p-1">Total</td><td className={num}>{(d.totals.billable_minutes / 60).toFixed(2)}</td><td className={num}>{money(d.totals.time_value_cents)}</td><td className={num}>{money(d.totals.charges_cents)}</td><td className={num}>{money(d.totals.total_cents)}</td><td /></tr></tfoot>}
          </table>
        </>
      )}
    </Card>
  );
}

function RecurringCard() {
  const [months, setMonths] = useState(12);
  const q = useQuery({ queryKey: ["report", "recurring", months], queryFn: () => api<RecurringReport>(`/reports/recurring?months=${months}`) });
  return (
    <Card title="Recurring revenue" actions={<a className={dl} href={`/api/reports/recurring.csv?months=${months}`}>Download CSV</a>}>
      <div className="w-32"><Field label="Months"><input className={inputCls} type="number" min={1} max={36} value={months} onChange={(e) => setMonths(Math.min(36, Math.max(1, Number(e.target.value) || 1)))} /></Field></div>
      <ErrorMsg error={q.error} />
      <p className="my-2 text-xs text-slate-500"><b>Contracted</b> applies today's quantity and price to every month (what the monthly run would bill); <b>invoiced</b> is what agreement lines were actually billed for that month.</p>
      {q.data && (
        <table className="w-full text-left text-sm">
          <thead className="border-b border-slate-200 text-slate-500"><tr><th className="p-1">Month</th><th className={num}>Clients</th><th className={num}>Agreements</th><th className={num}>Contracted</th><th className={num}>Invoiced</th></tr></thead>
          <tbody>{q.data.months.map((m) => <tr key={m.month} className="border-b border-slate-100"><td className="p-1">{m.month.slice(0, 7)}</td><td className={num}>{m.clients}</td><td className={num}>{m.agreements}</td><td className={num}>{money(m.contracted_cents)}</td><td className={num}>{money(m.invoiced_cents)}</td></tr>)}</tbody>
        </table>
      )}
    </Card>
  );
}

function InvoiceExport() {
  const { qs, inputs } = useRange();
  return (
    <Card title="Invoice export for your accountant" actions={<a className={dl} href={`/api/reports/invoices.csv${qs}`}>Download CSV</a>}>
      {inputs}
      <p className="mt-2 text-xs text-slate-500">One row per finalized or voided invoice by invoice date: totals, tax, paid, written off, balance and status, in dollars. Blank dates use the last 12 months.</p>
    </Card>
  );
}
