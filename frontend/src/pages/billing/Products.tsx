import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Product, api } from "../../api";
import { can, useMe } from "../../auth";
import { money, parseMoney } from "../../money";
import { Button, ErrorMsg, Field, inputCls } from "../../ui";

export default function Products() {
  const { data: me } = useMe();
  const canWrite = can(me, "billing:write");
  const qc = useQueryClient();
  const list = useQuery({ queryKey: ["products", "all"], queryFn: () => api<Product[]>("/products?include_archived=true") });
  const [f, setF] = useState({ sku: "", name: "", price: "", cost: "", taxable: true });
  const refresh = () => { qc.invalidateQueries({ queryKey: ["products"] }); };
  const create = useMutation({
    mutationFn: () => {
      const price = parseMoney(f.price), cost = f.cost ? parseMoney(f.cost) : null;
      if (price === null || (f.cost && cost === null)) throw new Error("Enter valid amounts, e.g. 899.00");
      return api("/products", { method: "POST", json: { sku: f.sku || null, name: f.name, unit_price_cents: price, cost_cents: cost, taxable: f.taxable } });
    },
    onSuccess: () => { setF({ sku: "", name: "", price: "", cost: "", taxable: true }); refresh(); },
  });
  const toggle = useMutation({ mutationFn: (p: Product) => api(`/products/${p.id}/${p.archived_at ? "unarchive" : "archive"}`, { method: "POST" }), onSuccess: refresh });
  return (
    <div className="space-y-4">
      <p className="text-sm text-slate-600">Catalog of things you resell. Prices are copied onto each sale when it is recorded, so changing a price here never changes past charges or invoices.</p>
      <ErrorMsg error={list.error ?? toggle.error} />
      <table className="w-full rounded-lg border border-slate-200 bg-white text-left text-sm">
        <thead className="border-b border-slate-200 text-slate-500"><tr><th className="p-2">SKU</th><th>Name</th><th className="text-right">Price</th><th className="text-right">Cost</th><th>Tax</th>{canWrite && <th />}</tr></thead>
        <tbody>
          {list.data?.map((p) => (
            <tr key={p.id} className={`border-b border-slate-100 ${p.archived_at ? "text-slate-400 line-through" : ""}`}>
              <td className="p-2">{p.sku}</td><td>{p.name}</td><td className="text-right">{money(p.unit_price_cents)}</td>
              <td className="text-right">{p.cost_cents === null ? "" : money(p.cost_cents)}</td><td>{p.taxable ? "taxable" : ""}</td>
              {canWrite && <td><Button variant="secondary" onClick={() => toggle.mutate(p)}>{p.archived_at ? "Restore" : "Archive"}</Button></td>}
            </tr>
          ))}
          {list.data?.length === 0 && <tr><td colSpan={6} className="p-3 text-slate-500">No products.</td></tr>}
        </tbody>
      </table>
      {canWrite && (
        <form className="flex flex-wrap items-end gap-2 rounded-lg border border-slate-200 bg-white p-4" onSubmit={(e) => { e.preventDefault(); create.mutate(); }}>
          <div className="w-32"><Field label="SKU"><input className={inputCls} value={f.sku} onChange={(e) => setF({ ...f, sku: e.target.value })} /></Field></div>
          <div className="w-64"><Field label="Name"><input className={inputCls} required value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field></div>
          <div className="w-28"><Field label="Price ($)"><input className={inputCls} required value={f.price} onChange={(e) => setF({ ...f, price: e.target.value })} /></Field></div>
          <div className="w-28"><Field label="Cost ($)"><input className={inputCls} value={f.cost} onChange={(e) => setF({ ...f, cost: e.target.value })} /></Field></div>
          <label className="flex items-center gap-1 pb-2 text-sm"><input type="checkbox" checked={f.taxable} onChange={(e) => setF({ ...f, taxable: e.target.checked })} />Taxable</label>
          <Button type="submit">Add product</Button><ErrorMsg error={create.error} />
        </form>
      )}
    </div>
  );
}
