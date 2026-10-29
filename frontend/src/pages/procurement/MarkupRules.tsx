import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useState } from "react";
import { AppSettings, MarkupRule, PRODUCT_CATEGORIES, Product, ProductCategory, api, bpPercent, procurement } from "../../api";
import { can, useMe } from "../../auth";
import { parsePercent } from "../../money";
import { Button, Card, ErrorMsg, Field, inputCls } from "../../ui";
import { ProcurementNav } from "./PurchaseOrders";

const pctText = (bp: number) => (bp / 100).toFixed(2);

export default function MarkupRules() {
  const { data: me } = useMe();
  const write = can(me, "billing:write");
  const qc = useQueryClient();
  const rules = useQuery({ queryKey: ["procurement", "markup"], queryFn: procurement.markupRules });
  const products = useQuery({ queryKey: ["products"], queryFn: () => api<Product[]>("/products"), enabled: can(me, "billing:read") });
  const refresh = () => qc.invalidateQueries({ queryKey: ["procurement", "markup"] });
  const remove = useMutation({ mutationFn: (id: number) => procurement.deleteMarkupRule(id), onSuccess: refresh });
  const name = (id: number) => products.data?.find((p) => p.id === id)?.name ?? `Product #${id}`;
  const byProduct = (rules.data ?? []).filter((r) => r.product_id !== null);
  const byCategory = (rules.data ?? []).filter((r) => r.category !== null);
  return (
    <div className="space-y-4">
      <ProcurementNav />
      <p className="text-sm text-slate-600">
        A delivered item is billed at cost plus markup. The markup comes from the first match: the line, then the product rule, then the category rule, then the default.
      </p>
      <DefaultMarkup write={write} />
      <ErrorMsg error={rules.error ?? remove.error} />
      {rules.isLoading && <p className="text-sm text-slate-500">Loading…</p>}
      {rules.data && rules.data.length === 0 && <p className="text-sm text-slate-500">No markup rules yet. Everything uses the default markup.</p>}
      <RuleTable title="Product rules" rules={byProduct} label={(r) => name(r.product_id as number)} write={write} onChange={refresh} onDelete={(r) => remove.mutate(r.id)} />
      <RuleTable title="Category rules" rules={byCategory} label={(r) => r.category as string} write={write} onChange={refresh} onDelete={(r) => remove.mutate(r.id)} />
      {write && <AddRule products={(products.data ?? []).filter((p) => !p.archived_at)} onDone={refresh} />}
    </div>
  );
}

function DefaultMarkup({ write }: { write: boolean }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["lookup", "settings"], queryFn: () => api<AppSettings & { default_markup_bp: number }>("/settings") });
  const [text, setText] = useState<string | null>(null);
  const [bad, setBad] = useState("");
  const save = useMutation({
    mutationFn: (bp: number) => api("/settings", { method: "PATCH", json: { default_markup_bp: bp } }),
    onSuccess: () => { setText(null); qc.invalidateQueries(); },
  });
  if (!q.data) return <ErrorMsg error={q.error} />;
  const shown = text ?? pctText(q.data.default_markup_bp);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const bp = parsePercent(shown);
    if (bp === null || bp > 100_000) return setBad("Enter a percent such as 15 or 8.25.");
    setBad("");
    save.mutate(bp);
  };
  return (
    <Card title="Default markup">
      <form onSubmit={submit} className="flex flex-wrap items-end gap-2">
        <div className="w-40">
          <Field label="Default markup (%)"><input className={inputCls} inputMode="decimal" disabled={!write} value={shown} onChange={(e) => setText(e.target.value)} /></Field>
        </div>
        {write && text !== null && <Button type="submit" disabled={save.isPending}>Save default</Button>}
        {!write && <span className="text-sm text-slate-500">Currently {bpPercent(q.data.default_markup_bp)}</span>}
      </form>
      {bad && <p role="alert" className="mt-2 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{bad}</p>}
      <ErrorMsg error={save.error} />
    </Card>
  );
}

function RuleTable({ title, rules, label, write, onChange, onDelete }: {
  title: string; rules: MarkupRule[]; label: (r: MarkupRule) => string; write: boolean; onChange: () => void; onDelete: (r: MarkupRule) => void;
}) {
  const [edit, setEdit] = useState<{ id: number; text: string } | null>(null);
  const [bad, setBad] = useState("");
  const save = useMutation({
    mutationFn: ({ id, bp }: { id: number; bp: number }) => procurement.updateMarkupRule(id, bp),
    onSuccess: () => { setEdit(null); setBad(""); onChange(); },
  });
  if (rules.length === 0) return null;
  const commit = (r: MarkupRule) => {
    const bp = parsePercent(edit?.text ?? "");
    if (bp === null || bp > 100_000) return setBad("Enter a percent such as 15 or 8.25.");
    setBad("");
    save.mutate({ id: r.id, bp });
  };
  return (
    <Card title={title}>
      <table className="w-full text-sm">
        <caption className="sr-only">{title}</caption>
        <thead>
          <tr className="border-b border-slate-200 text-left text-slate-500">
            <th scope="col" className="py-1.5">Applies to</th><th scope="col">Markup</th><th scope="col"><span className="sr-only">Actions</span></th>
          </tr>
        </thead>
        <tbody>
          {rules.map((r) => (
            <tr key={r.id} className="border-b border-slate-100">
              <td className="py-1.5 capitalize">{label(r)}</td>
              <td>
                {write && edit?.id === r.id ? (
                  <input aria-label={`Markup for ${label(r)} (%)`} aria-invalid={bad ? true : undefined} aria-describedby={bad ? `${title.replace(/\s+/g, "-")}-error` : undefined} className={inputCls + " max-w-[8rem]"} inputMode="decimal" value={edit.text} onChange={(e) => setEdit({ id: r.id, text: e.target.value })} />
                ) : bpPercent(r.markup_bp)}
              </td>
              <td className="text-right">
                {write && (
                  <span className="flex justify-end gap-2">
                    {edit?.id === r.id ? (
                      <>
                        <Button aria-label={`Save ${label(r)}`} disabled={save.isPending} onClick={() => commit(r)}>Save</Button>
                        <Button variant="secondary" aria-label={`Cancel editing ${label(r)}`} onClick={() => { setEdit(null); setBad(""); }}>Cancel</Button>
                      </>
                    ) : (
                      <Button variant="secondary" aria-label={`Edit ${label(r)} markup`} onClick={() => { setBad(""); setEdit({ id: r.id, text: pctText(r.markup_bp) }); }}>Edit</Button>
                    )}
                    <Button variant="danger" aria-label={`Delete ${label(r)} rule`} onClick={() => { if (window.confirm("Delete this rule? Items already delivered keep their price.")) onDelete(r); }}>Delete</Button>
                  </span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {bad && <p id={`${title.replace(/\s+/g, "-")}-error`} role="alert" className="mt-2 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{bad}</p>}
      <ErrorMsg error={save.error} />
    </Card>
  );
}

function AddRule({ products, onDone }: { products: Product[]; onDone: () => void }) {
  const [target, setTarget] = useState<"product" | "category">("category");
  const [productId, setProductId] = useState("");
  const [category, setCategory] = useState<ProductCategory>("hardware");
  const [pct, setPct] = useState("");
  const [bad, setBad] = useState("");
  const add = useMutation({
    mutationFn: (json: Parameters<typeof procurement.createMarkupRule>[0]) => procurement.createMarkupRule(json),
    onSuccess: () => { setPct(""); setProductId(""); onDone(); },
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const bp = parsePercent(pct);
    if (bp === null || bp > 100_000) return setBad("Enter a percent such as 15 or 8.25.");
    if (target === "product" && !productId) return setBad("Choose a product.");
    setBad("");
    add.mutate(target === "product" ? { product_id: Number(productId), markup_bp: bp } : { category, markup_bp: bp });
  };
  return (
    <Card title="Add a rule">
      <form onSubmit={submit} className="flex flex-wrap items-end gap-3">
        <Field label="Rule for">
          <select className={inputCls} value={target} onChange={(e) => setTarget(e.target.value as "product" | "category")}>
            <option value="category">A category</option><option value="product">A product</option>
          </select>
        </Field>
        {target === "category" ? (
          <Field label="Category">
            <select className={inputCls} value={category} onChange={(e) => setCategory(e.target.value as ProductCategory)}>
              {PRODUCT_CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </Field>
        ) : (
          <Field label="Product">
            <select className={inputCls} value={productId} onChange={(e) => setProductId(e.target.value)}>
              <option value="">Choose a product</option>
              {products.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </Field>
        )}
        <div className="w-36"><Field label="New rule markup (%)"><input className={inputCls} inputMode="decimal" value={pct} onChange={(e) => setPct(e.target.value)} /></Field></div>
        <Button type="submit" disabled={add.isPending}>Add rule</Button>
      </form>
      {bad && <p role="alert" className="mt-2 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{bad}</p>}
      <ErrorMsg error={add.error} />
    </Card>
  );
}
