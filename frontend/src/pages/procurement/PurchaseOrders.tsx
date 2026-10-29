import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useState } from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";
import { Organization, PoLineInput, PoStatus, Product, api, bpPercent, procurement } from "../../api";
import { can, useMe } from "../../auth";
import { money, parseMoney, parsePercent } from "../../money";
import { Button, Card, ErrorMsg, Field, inputCls } from "../../ui";
import Vendors from "./Vendors";

export const PO_STATUS_LABEL: Record<PoStatus, string> = {
  draft: "Draft", ordered: "Ordered", partial: "Partly received", received: "Received", cancelled: "Cancelled",
};
const STATUSES: PoStatus[] = ["draft", "ordered", "partial", "received", "cancelled"];

/** Section links shared by every procurement page. */
export function ProcurementNav() {
  const tab = ({ isActive }: { isActive: boolean }) =>
    `rounded-t px-3 py-1.5 text-sm ${isActive ? "border-b-2 border-blue-600 font-medium" : "text-slate-600 hover:bg-slate-100"}`;
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold tracking-tight">Procurement</h1>
      <nav aria-label="Procurement sections" className="flex gap-1 border-b border-slate-200">
        <NavLink end to="/procurement" className={tab}>Orders and vendors</NavLink>
        <NavLink to="/procurement/inventory" className={tab}>Inventory</NavLink>
        <NavLink to="/procurement/markup" className={tab}>Markup rules</NavLink>
      </nav>
    </div>
  );
}

export default function PurchaseOrders() {
  const [tab, setTab] = useState<"orders" | "vendors">("orders");
  const tabCls = (on: boolean) => `rounded-lg px-3 py-1.5 text-sm ${on ? "bg-blue-50 font-semibold text-blue-700" : "text-slate-600 hover:bg-slate-100"}`;
  return (
    <div className="space-y-4">
      <ProcurementNav />
      <div role="group" aria-label="Orders or vendors" className="flex gap-2">
        <button type="button" aria-pressed={tab === "orders"} className={tabCls(tab === "orders")} onClick={() => setTab("orders")}>Purchase orders</button>
        <button type="button" aria-pressed={tab === "vendors"} className={tabCls(tab === "vendors")} onClick={() => setTab("vendors")}>Vendors</button>
      </div>
      {tab === "orders" ? <OrderList /> : <Vendors />}
    </div>
  );
}

function OrderList() {
  const { data: me } = useMe();
  const write = can(me, "procurement:write");
  const [status, setStatus] = useState<PoStatus | "">("");
  const [adding, setAdding] = useState(false);
  const q = useQuery({ queryKey: ["procurement", "pos", status], queryFn: () => procurement.purchaseOrders({ status }) });
  const rows = q.data ?? [];
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <Field label="Status">
          <select className={inputCls} value={status} onChange={(e) => setStatus(e.target.value as PoStatus | "")}>
            <option value="">All</option>
            {STATUSES.map((s) => <option key={s} value={s}>{PO_STATUS_LABEL[s]}</option>)}
          </select>
        </Field>
        {write && <Button onClick={() => setAdding(!adding)}>{adding ? "Close" : "New purchase order"}</Button>}
      </div>
      {write && adding && <NewPo />}
      <ErrorMsg error={q.error} />
      {q.isLoading && <p className="text-sm text-slate-500">Loading…</p>}
      {q.data && rows.length === 0 && <p className="text-sm text-slate-500">No purchase orders yet.</p>}
      {rows.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <caption className="sr-only">Purchase orders</caption>
            <thead>
              <tr className="border-b border-slate-200 text-left text-slate-500">
                <th scope="col" className="py-1.5">Number</th><th scope="col">Vendor</th><th scope="col">Status</th>
                <th scope="col">Ordered</th><th scope="col">Expected</th><th scope="col" className="text-right">Total cost</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((p) => (
                <tr key={p.id} className="border-b border-slate-100">
                  <td className="py-1.5">
                    <Link className="text-blue-700 hover:underline" to={`/procurement/purchase-orders/${p.id}`}>{p.number ?? `Draft #${p.id}`}</Link>
                  </td>
                  <td>{p.vendor_name ?? "—"}</td>
                  <td>{PO_STATUS_LABEL[p.status]}</td>
                  <td>{p.ordered_on ?? "—"}</td>
                  <td>{p.expected_on ?? "—"}</td>
                  <td className="text-right">{money(p.lines.reduce((t, l) => t + l.quantity * l.unit_cost_cents, 0))}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

const blankLine = { product_id: "", description: "", quantity: "1", cost: "", serialised: false, billable: true, taxable: "", markup: "" };
type LineDraft = typeof blankLine;

function NewPo() {
  const { data: me } = useMe();
  const qc = useQueryClient();
  const nav = useNavigate();
  const vendors = useQuery({ queryKey: ["procurement", "vendors", false], queryFn: () => procurement.vendors(false) });
  const orgs = useQuery({ queryKey: ["orgs-all"], queryFn: () => api<Organization[] | { items: Organization[] }>("/organizations") });
  const products = useQuery({ queryKey: ["products"], queryFn: () => api<Product[]>("/products"), enabled: can(me, "billing:read") });
  const orgList = Array.isArray(orgs.data) ? orgs.data : orgs.data?.items ?? [];
  const [f, setF] = useState({ vendor_id: "", organization_id: "", expected_on: "", vendor_reference: "", notes: "" });
  const [lines, setLines] = useState<LineDraft[]>([{ ...blankLine }]);
  const [bad, setBad] = useState("");
  const create = useMutation({
    mutationFn: (json: Parameters<typeof procurement.createPurchaseOrder>[0]) => procurement.createPurchaseOrder(json),
    onSuccess: (po) => {
      qc.invalidateQueries({ queryKey: ["procurement"] });
      nav(`/procurement/purchase-orders/${po.id}`);
    },
  });
  const setLine = (i: number, patch: Partial<LineDraft>) => setLines(lines.map((l, j) => (j === i ? { ...l, ...patch } : l)));
  const pickProduct = (i: number, id: string) => {
    const p = products.data?.find((x) => String(x.id) === id);
    setLine(i, { product_id: id, ...(p ? { description: p.name, cost: p.cost_cents != null ? (p.cost_cents / 100).toFixed(2) : "" } : {}) });
  };
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const out: PoLineInput[] = [];
    for (const [i, l] of lines.entries()) {
      const n = i + 1;
      const quantity = Number(l.quantity);
      if (!Number.isInteger(quantity) || quantity < 1) return setBad(`Line ${n}: quantity must be a whole number, 1 or more.`);
      const cost = l.cost.trim() === "" ? null : parseMoney(l.cost);
      if (cost !== null && cost < 0) return setBad(`Line ${n}: enter the unit cost, for example 123.45.`);
      if (l.cost.trim() !== "" && cost === null) return setBad(`Line ${n}: enter the unit cost, for example 123.45.`);
      const markup = l.markup.trim() === "" ? null : parsePercent(l.markup);
      if (l.markup.trim() !== "" && markup === null) return setBad(`Line ${n}: enter the markup as a percent, for example 15 or 8.25.`);
      if (!l.product_id && !l.description.trim()) return setBad(`Line ${n}: pick a product or type a description.`);
      if (!l.product_id && cost === null) return setBad(`Line ${n}: a free-text line needs a unit cost.`);
      out.push({
        product_id: l.product_id ? Number(l.product_id) : null,
        description: l.description.trim() || null,
        quantity,
        unit_cost_cents: cost,
        serialised: l.serialised,
        billable: l.billable,
        taxable: l.taxable === "" ? null : l.taxable === "yes",
        markup_bp: markup,
      });
    }
    setBad("");
    create.mutate({
      vendor_id: Number(f.vendor_id),
      organization_id: f.organization_id ? Number(f.organization_id) : null,
      expected_on: f.expected_on || null,
      vendor_reference: f.vendor_reference.trim() || null,
      notes: f.notes.trim() || null,
      lines: out,
    });
  };
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
  return (
    <Card title="New purchase order">
      <form onSubmit={submit} className="space-y-3">
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Vendor">
            <select required className={inputCls} value={f.vendor_id} onChange={set("vendor_id")}>
              <option value="">Choose a vendor</option>
              {(vendors.data ?? []).map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
            </select>
          </Field>
          <Field label="Client (optional)">
            <select className={inputCls} value={f.organization_id} onChange={set("organization_id")}>
              <option value="">Stock for general use</option>
              {orgList.filter((o) => !o.archived_at).map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
            </select>
          </Field>
          <Field label="Expected on"><input type="date" className={inputCls} value={f.expected_on} onChange={set("expected_on")} /></Field>
          <Field label="Vendor reference"><input className={inputCls} value={f.vendor_reference} onChange={set("vendor_reference")} /></Field>
          <div className="sm:col-span-2"><Field label="Notes"><input className={inputCls} value={f.notes} onChange={set("notes")} /></Field></div>
        </div>
        {vendors.data && vendors.data.length === 0 && <p className="text-sm text-slate-500">Add a vendor first (Vendors tab).</p>}
        <fieldset className="space-y-3">
          <legend className="text-sm font-medium text-slate-700">Lines</legend>
          {lines.map((l, i) => (
            <div key={i} className="grid gap-2 rounded-lg border border-slate-200 p-3 sm:grid-cols-6">
              <div className="sm:col-span-2">
                <Field label={`Line ${i + 1} product`}>
                  <select className={inputCls} value={l.product_id} onChange={(e) => pickProduct(i, e.target.value)}>
                    <option value="">Free text</option>
                    {(products.data ?? []).filter((p) => !p.archived_at).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                  </select>
                </Field>
              </div>
              <div className="sm:col-span-2"><Field label={`Line ${i + 1} description`}><input className={inputCls} value={l.description} onChange={(e) => setLine(i, { description: e.target.value })} /></Field></div>
              <Field label={`Line ${i + 1} quantity`}><input className={inputCls} type="number" min={1} value={l.quantity} onChange={(e) => setLine(i, { quantity: e.target.value })} /></Field>
              <Field label={`Line ${i + 1} unit cost ($)`}><input className={inputCls} inputMode="decimal" value={l.cost} onChange={(e) => setLine(i, { cost: e.target.value })} /></Field>
              <Field label={`Line ${i + 1} markup (%)`}><input className={inputCls} inputMode="decimal" placeholder="Rule default" value={l.markup} onChange={(e) => setLine(i, { markup: e.target.value })} /></Field>
              <Field label={`Line ${i + 1} taxable`}>
                <select className={inputCls} value={l.taxable} onChange={(e) => setLine(i, { taxable: e.target.value })}>
                  <option value="">From product</option><option value="yes">Yes</option><option value="no">No</option>
                </select>
              </Field>
              <div className="flex items-end gap-4 text-sm">
                <label className="flex items-center gap-1"><input type="checkbox" checked={l.serialised} onChange={(e) => setLine(i, { serialised: e.target.checked })} />{`Line ${i + 1} serialised`}</label>
                <label className="flex items-center gap-1"><input type="checkbox" checked={l.billable} onChange={(e) => setLine(i, { billable: e.target.checked })} />{`Line ${i + 1} billable`}</label>
              </div>
              <div className="flex items-end">
                {lines.length > 1 && <Button type="button" variant="secondary" aria-label={`Remove line ${i + 1}`} onClick={() => setLines(lines.filter((_, j) => j !== i))}>Remove</Button>}
              </div>
            </div>
          ))}
          <Button type="button" variant="secondary" onClick={() => setLines([...lines, { ...blankLine }])}>Add line</Button>
        </fieldset>
        {bad && <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{bad}</p>}
        <ErrorMsg error={create.error} />
        <Button type="submit" disabled={create.isPending || !f.vendor_id}>Create purchase order</Button>
        <p className="text-xs text-slate-500">Markup is a percent such as 15 ({bpPercent(1500)}); leave it blank to use the markup rules.</p>
      </form>
    </Card>
  );
}
