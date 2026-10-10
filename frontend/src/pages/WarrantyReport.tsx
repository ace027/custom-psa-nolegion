import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { Organization, Page, WARRANTY_LABEL, WarrantyReport as Report, WarrantyState, api } from "../api";
import { Card, ErrorMsg, Field, WarrantyBadge, inputCls } from "../ui";

export default function WarrantyReport() {
  const [org, setOrg] = useState("");
  const [window, setWindow] = useState("");
  const [status, setStatus] = useState("");
  const qs = new URLSearchParams({ ...(org ? { organization_id: org } : {}), ...(window ? { within_days: window } : {}), ...(status ? { status } : {}) }).toString();
  const suffix = qs ? `?${qs}` : "";
  const orgs = useQuery({ queryKey: ["orgs-all"], queryFn: () => api<Page<Organization>>("/organizations?limit=200") });
  const q = useQuery({ queryKey: ["warranty", qs], queryFn: () => api<Report>(`/reports/warranty${suffix}`) });
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold tracking-tight">Warranty</h1>
      <Card title="Devices by warranty" actions={<a className="text-sm text-blue-700 hover:underline" href={`/api/reports/warranty.csv${suffix}`}>Download CSV</a>}>
        <div className="flex flex-wrap gap-3">
          <Field label="Client">
            <select className={inputCls} value={org} onChange={(e) => setOrg(e.target.value)}>
              <option value="">All clients</option>
              {orgs.data?.items.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
            </select>
          </Field>
          <Field label="Expiring within">
            <select className={inputCls} value={window} onChange={(e) => setWindow(e.target.value)}>
              <option value="">Any time</option>
              <option value="30">30 days (and expired)</option>
              <option value="60">60 days (and expired)</option>
              <option value="90">90 days (and expired)</option>
              <option value="180">180 days (and expired)</option>
            </select>
          </Field>
          <Field label="Status">
            <select className={inputCls} value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">Any</option>
              {(Object.keys(WARRANTY_LABEL) as WarrantyState[]).map((s) => <option key={s} value={s}>{WARRANTY_LABEL[s]}</option>)}
            </select>
          </Field>
        </div>
        <ErrorMsg error={q.error} />
        {q.data && (
          <>
            <p className="my-2 text-xs text-slate-500">
              As of {q.data.as_of}. {q.data.total} device(s):{" "}
              {(Object.keys(q.data.counts) as WarrantyState[]).filter((s) => q.data.counts[s] > 0).map((s) => `${q.data.counts[s]} ${WARRANTY_LABEL[s].toLowerCase()}`).join(", ") || "none"}.
              Devices with no date are shown as unknown, never guessed.
            </p>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-slate-200 text-slate-500"><tr><th className="p-1">Client</th><th>Device</th><th>Type</th><th>Make / model</th><th>Serial</th><th>Warranty ends</th></tr></thead>
                <tbody>
                  {q.data.rows.map((a) => (
                    <tr key={a.id} className="border-b border-slate-100">
                      <td className="p-1"><Link className="text-blue-700 hover:underline" to={`/organizations/${a.organization_id}`}>{a.organization_name}</Link></td>
                      <td>{a.name}</td><td>{a.kind}</td>
                      <td>{[a.manufacturer, a.model].filter(Boolean).join(" ") || "—"}</td>
                      <td>{a.serial ?? "—"}</td>
                      <td>{a.warranty_end ?? "—"} <WarrantyBadge state={a.warranty_status} label={WARRANTY_LABEL[a.warranty_status]} /></td>
                    </tr>
                  ))}
                  {q.data.rows.length === 0 && <tr><td colSpan={6} className="p-2 text-slate-500">No devices match.</td></tr>}
                </tbody>
              </table>
            </div>
          </>
        )}
      </Card>
    </div>
  );
}
