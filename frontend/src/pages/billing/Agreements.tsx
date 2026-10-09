import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Agreement, Organization, Page, api } from "../../api";
import { can, useMe } from "../../auth";
import { money, parseMoney } from "../../money";
import { Button, ErrorMsg, Field, fmt, inputCls } from "../../ui";

const TYPE_LABEL = { per_user: "Per user", per_device: "Per device", flat: "Flat fee", block: "Block hours" };

export default function Agreements() {
  const { data: me } = useMe();
  const canWrite = can(me, "billing:write");
  const qc = useQueryClient();
  const list = useQuery({ queryKey: ["agreements"], queryFn: () => api<Agreement[]>("/agreements") });
  const orgs = useQuery({ queryKey: ["orgs", "", false], queryFn: () => api<Page<Organization>>("/organizations?limit=200&include_archived=false&q=") });
  const blank = { organization_id: "", name: "", type: "per_user", price: "", quantity: "1", hours: "", taxable: false, start_date: new Date().toISOString().slice(0, 10) };
  const [f, setF] = useState(blank);
  const create = useMutation({
    mutationFn: () => {
      const cents = parseMoney(f.price);
      if (cents === null) throw new Error("Enter a valid price, e.g. 12.00");
      const isBlock = f.type === "block";
      const hours = Number(f.hours);
      if (isBlock && !(hours > 0)) throw new Error("Enter the included hours, e.g. 10 or 7.5");
      return api("/agreements", { method: "POST", json: { organization_id: Number(f.organization_id), name: f.name, type: f.type, unit_price_cents: cents, quantity: f.type === "flat" || isBlock ? 1 : Number(f.quantity), block_minutes: isBlock ? Math.round(hours * 60) : null, taxable: f.taxable, start_date: f.start_date } });
    },
    onSuccess: () => { setF(blank); qc.invalidateQueries({ queryKey: ["agreements"] }); },
  });
  const total = (list.data ?? []).filter((a) => !a.end_date).reduce((s, a) => s + a.monthly_amount_cents, 0);
  return (
    <div className="space-y-4">
      <p className="text-sm text-slate-600">Recurring monthly charges. Per-user and per-device quantities are entered by hand here (and later can be filled by integrations). The monthly run bills the quantity <b>as it is on the day you start the run</b>. An agreement that starts or ends mid-month is billed in full plus a separate negative <b>proration</b> line for the calendar days not covered.</p>
      <ErrorMsg error={list.error} />
      <table className="w-full rounded-lg border border-slate-200 bg-surface text-left text-sm">
        <thead className="border-b border-slate-200 text-slate-500"><tr><th className="p-2">Client</th><th>Agreement</th><th>Type</th><th className="text-right">Unit</th><th>Qty</th><th className="text-right">Monthly</th><th>Dates</th>{canWrite && <th />}</tr></thead>
        <tbody>
          {list.data?.map((a) => <Row key={a.id} a={a} canWrite={canWrite} />)}
          {list.data?.length === 0 && <tr><td colSpan={8} className="p-3 text-slate-500">No agreements.</td></tr>}
        </tbody>
        <tfoot><tr><td colSpan={5} className="p-2 text-right text-slate-500">Active monthly recurring (before tax)</td><td className="text-right font-semibold">{money(total)}</td><td colSpan={2} /></tr></tfoot>
      </table>
      {canWrite && (
        <form className="grid gap-2 rounded-lg border border-slate-200 bg-surface p-4 sm:grid-cols-4" onSubmit={(e) => { e.preventDefault(); create.mutate(); }}>
          <h2 className="col-span-full font-semibold">New agreement</h2>
          <Field label="Client"><select className={inputCls} required value={f.organization_id} onChange={(e) => setF({ ...f, organization_id: e.target.value })}><option value="">Select…</option>{orgs.data?.items.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}</select></Field>
          <Field label="Name"><input className={inputCls} required value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
          <Field label="Type"><select className={inputCls} value={f.type} onChange={(e) => setF({ ...f, type: e.target.value, hours: e.target.value === "block" ? f.hours : "" })}>{Object.entries(TYPE_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></Field>
          <Field label={f.type === "flat" || f.type === "block" ? "Monthly fee ($)" : "Price per unit ($)"}><input className={inputCls} required value={f.price} onChange={(e) => setF({ ...f, price: e.target.value })} /></Field>
          {f.type === "block" && <Field label="Included hours"><input className={inputCls} type="number" min={0} step={0.25} required value={f.hours} onChange={(e) => setF({ ...f, hours: e.target.value })} /></Field>}
          {f.type !== "flat" && f.type !== "block" && <Field label={f.type === "per_user" ? "Users" : "Devices"}><input className={inputCls} type="number" min={0} value={f.quantity} onChange={(e) => setF({ ...f, quantity: e.target.value })} /></Field>}
          <Field label="Starts"><input className={inputCls} type="date" required value={f.start_date} onChange={(e) => setF({ ...f, start_date: e.target.value })} /></Field>
          <label className="flex items-end gap-1 pb-2 text-sm"><input type="checkbox" checked={f.taxable} onChange={(e) => setF({ ...f, taxable: e.target.checked })} />Taxable</label>
          <div className="col-span-full space-y-2"><ErrorMsg error={create.error} /><Button type="submit">Create agreement</Button></div>
        </form>
      )}
    </div>
  );
}

function Row({ a, canWrite }: { a: Agreement; canWrite: boolean }) {
  const qc = useQueryClient();
  const [qtyText, setQty] = useState(String(a.quantity));
  const [reason, setReason] = useState("");
  const [hoursText, setHours] = useState(a.block_minutes == null ? "" : String(a.block_minutes / 60));
  const [showLog, setShowLog] = useState(false);
  const save = useMutation({
    mutationFn: () => api(`/agreements/${a.id}`, { method: "PATCH", json: { quantity: Number(qtyText), reason: reason || null } }),
    onSuccess: () => { setReason(""); qc.invalidateQueries({ queryKey: ["agreements"] }); qc.invalidateQueries({ queryKey: ["qlog", a.id] }); },
  });
  const saveHours = useMutation({
    mutationFn: () => {
      const h = Number(hoursText);
      if (!(h > 0)) throw new Error("Enter the included hours, e.g. 10 or 7.5");
      return api(`/agreements/${a.id}`, { method: "PATCH", json: { block_minutes: Math.round(h * 60) } });
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["agreements"] }),
  });
  const end = useMutation({
    mutationFn: (end_date: string | null) => api(`/agreements/${a.id}`, { method: "PATCH", json: { end_date } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["agreements"] }),
  });
  const suggest = useQuery({
    queryKey: ["device-count", a.id, a.quantity],
    enabled: canWrite && a.type === "per_device" && !a.end_date,
    queryFn: () => api<{ ninjaone_devices: number; agreement_quantity: number; differs: boolean }>(`/agreements/${a.id}/device-count`),
  });
  const adopt = useMutation({
    mutationFn: (n: number) => api(`/agreements/${a.id}`, { method: "PATCH", json: { quantity: n, reason: "Updated from NinjaOne device count" } }),
    onSuccess: (_d, n) => { setQty(String(n)); qc.invalidateQueries({ queryKey: ["agreements"] }); qc.invalidateQueries({ queryKey: ["qlog", a.id] }); },
  });
  const log = useQuery({ queryKey: ["qlog", a.id], enabled: showLog, queryFn: () => api<{ id: number; old_quantity: number | null; new_quantity: number; reason: string | null; changed_at: string }[]>(`/agreements/${a.id}/quantity-log`) });
  return (
    <>
      <tr className={`border-b border-slate-100 ${a.end_date ? "text-slate-400" : ""}`}>
        <td className="p-2">{a.organization_name}</td><td>{a.name}</td><td>{TYPE_LABEL[a.type]}{a.type === "block" && a.block_minutes != null && <span className="text-slate-500"> ({a.block_minutes / 60} h included)</span>}</td>
        <td className="text-right">{money(a.unit_price_cents)}</td>
        <td>{canWrite && a.type !== "flat" && a.type !== "block" ? (
          <span className="flex items-center gap-1"><input aria-label={`${a.name} quantity`} className={inputCls + " w-20"} type="number" min={0} value={qtyText} onChange={(e) => setQty(e.target.value)} />
            {Number(qtyText) !== a.quantity && <><input aria-label="Reason" placeholder="why?" className={inputCls + " w-32"} value={reason} onChange={(e) => setReason(e.target.value)} /><Button onClick={() => save.mutate()}>Save</Button></>}</span>
        ) : a.type === "block" && canWrite ? (
          <span className="flex items-center gap-1"><input aria-label={`${a.name} included hours`} className={inputCls + " w-20"} type="number" min={0} step={0.25} value={hoursText} onChange={(e) => setHours(e.target.value)} />h
            {Math.round(Number(hoursText) * 60) !== a.block_minutes && <Button onClick={() => saveHours.mutate()}>Save</Button>}</span>
        ) : a.quantity}</td>
        <td className="text-right">{money(a.monthly_amount_cents)}</td>
        <td className="whitespace-nowrap">{a.start_date} → {a.end_date ?? "ongoing"}</td>
        <td className="whitespace-nowrap">
          <button className="text-blue-700 hover:underline" onClick={() => setShowLog(!showLog)}>history</button>
          {canWrite && (a.end_date ? <button className="ml-2 text-blue-700 hover:underline" onClick={() => end.mutate(null)}>resume</button> : <button className="ml-2 text-red-700 hover:underline" onClick={() => { const d = window.prompt("Last day of service (YYYY-MM-DD):", new Date().toISOString().slice(0, 10)); if (d) end.mutate(d); }}>end</button>)}
        </td>
      </tr>
      {suggest.data?.differs && (
        <tr><td colSpan={8} className="bg-amber-50 p-2 text-xs text-amber-900">
          NinjaOne reports {suggest.data.ninjaone_devices} devices; this agreement says {suggest.data.agreement_quantity}.{" "}
          <button className="text-blue-700 hover:underline" onClick={() => adopt.mutate(suggest.data.ninjaone_devices)}>Update quantity to {suggest.data.ninjaone_devices}</button>
          <span className="text-slate-600"> (nothing changes unless you click)</span>
        </td></tr>
      )}
      {(save.error || end.error || adopt.error || saveHours.error) && <tr><td colSpan={8}><ErrorMsg error={save.error ?? end.error ?? adopt.error ?? saveHours.error} /></td></tr>}
      {showLog && <tr><td colSpan={8} className="bg-slate-50 p-2 text-xs">{log.data?.map((l) => <div key={l.id}>{fmt(l.changed_at)}: {l.old_quantity ?? "—"} → {l.new_quantity}{l.reason ? ` (${l.reason})` : ""}</div>)}</td></tr>}
    </>
  );
}
