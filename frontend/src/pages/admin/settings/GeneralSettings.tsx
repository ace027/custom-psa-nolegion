import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { AppSettings, api } from "../../../api";
import TimezoneSelect from "../../../components/TimezoneSelect";
import { Button, Card, ErrorMsg, Field, inputCls } from "../../../ui";

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export default function GeneralSettings() {
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold tracking-tight">General</h1>
      <HoursCard />
      <InvoicingCard />
    </div>
  );
}

function HoursCard() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["lookup", "settings"], queryFn: () => api<AppSettings>("/settings") });
  const [edit, setEdit] = useState<AppSettings | null>(null);
  const s = edit ?? q.data;
  const save = useMutation({
    mutationFn: () => api("/settings", { method: "PATCH", json: edit }),
    onSuccess: () => {
      setEdit(null);
      qc.invalidateQueries();
    },
  });
  if (!s) return null;
  const hhmm = (m: number) => `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
  const toMin = (v: string) => Number(v.slice(0, 2)) * 60 + Number(v.slice(3, 5));
  const upd = (patch: Partial<AppSettings>) => setEdit({ ...s, ...patch });
  return (
    <Card title="Business hours, SLA and billing">
      <div className="grid gap-3 sm:grid-cols-4">
        <TimezoneSelect value={s.timezone} onChange={(timezone) => upd({ timezone })} />
        <Field label="Opens"><input className={inputCls} type="time" value={hhmm(s.business_start_minute)} onChange={(e) => upd({ business_start_minute: toMin(e.target.value) })} /></Field>
        <Field label="Closes"><input className={inputCls} type="time" value={hhmm(s.business_end_minute)} onChange={(e) => upd({ business_end_minute: toMin(e.target.value) })} /></Field>
        <Field label="Billing increment (min)"><input className={inputCls} type="number" min={1} value={s.billing_increment_minutes} onChange={(e) => upd({ billing_increment_minutes: Number(e.target.value) })} /></Field>
        <Field label="'At risk' when this % of SLA time is left"><input className={inputCls} type="number" min={0} max={100} value={s.sla_at_risk_percent} onChange={(e) => upd({ sla_at_risk_percent: Number(e.target.value) })} /></Field>
        <div className="col-span-full flex gap-3 text-sm">
          {DAYS.map((d, i) => (
            <label key={d} className="flex items-center gap-1">
              <input type="checkbox" checked={s.business_days.includes(i)} onChange={(e) => upd({ business_days: e.target.checked ? [...s.business_days, i] : s.business_days.filter((x) => x !== i) })} />
              {d}
            </label>
          ))}
        </div>
      </div>
      <p className="mt-2 text-xs text-slate-500">Changes apply to new tickets and future SLA calculations; existing due dates are recomputed only when a ticket's priority or pause state changes. Holidays work the same way.</p>
      <ErrorMsg error={save.error} />
      {edit && <div className="mt-2"><Button onClick={() => save.mutate()}>Save</Button></div>}
    </Card>
  );
}

function InvoicingCard() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["lookup", "settings"], queryFn: () => api<AppSettings>("/settings") });
  const [edit, setEdit] = useState<Partial<AppSettings>>({});
  const save = useMutation({
    mutationFn: () => api("/settings", { method: "PATCH", json: edit }),
    onSuccess: () => { setEdit({}); qc.invalidateQueries(); },
  });
  if (!q.data) return null;
  const v = { ...q.data, ...edit };
  return (
    <Card title="Invoicing: your company details">
      <p className="mb-2 text-sm text-slate-600">Printed on every invoice PDF. They are copied onto each invoice when it is finalized, so later changes never alter old invoices. Finalizing is blocked until a company name is set.</p>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Company name"><input className={inputCls} value={v.company_name ?? ""} onChange={(e) => setEdit({ ...edit, company_name: e.target.value })} /></Field>
        <Field label="Company address"><textarea className={inputCls} rows={2} value={v.company_address ?? ""} onChange={(e) => setEdit({ ...edit, company_address: e.target.value })} /></Field>
        <div className="sm:col-span-2"><Field label="Invoice footer (payment instructions, thank-you...)"><textarea className={inputCls} rows={2} value={v.invoice_footer ?? ""} onChange={(e) => setEdit({ ...edit, invoice_footer: e.target.value })} /></Field></div>
      </div>
      <ErrorMsg error={save.error} />
      {Object.keys(edit).length > 0 && <div className="mt-2"><Button onClick={() => save.mutate()}>Save</Button></div>}
    </Card>
  );
}
