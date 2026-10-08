import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Expense, Lookup, Organization, api } from "../api";
import { money, parseMoney, parsePercent, percent } from "../money";
import { Button, Card, ErrorMsg, Field, inputCls } from "../ui";

const today = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};
const blank = () => ({ kind: "expense" as "expense" | "mileage", date: today(), category_id: "", description: "", amount: "", miles: "", reimbursable: true, billable: false, taxable: false, markup: "", organization_id: "" });

export default function Expenses() {
  const qc = useQueryClient();
  const list = useQuery({ queryKey: ["expenses"], queryFn: () => api<Expense[]>("/expenses") });
  const cats = useQuery({ queryKey: ["lookup", "expense-categories"], queryFn: () => api<Lookup[]>("/expense-categories") });
  const orgs = useQuery({ queryKey: ["orgs-all"], queryFn: () => api<Organization[] | { items: Organization[] }>("/organizations") });
  const orgList = Array.isArray(orgs.data) ? orgs.data : orgs.data?.items ?? [];
  const [f, setF] = useState(blank());
  const [file, setFile] = useState<File | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const refresh = () => qc.invalidateQueries({ queryKey: ["expenses"] });

  const add = useMutation({
    mutationFn: async () => {
      const amount = f.kind === "expense" ? parseMoney(f.amount) : null;
      const markup = f.markup.trim() === "" ? 0 : parsePercent(f.markup);
      if (f.kind === "expense" && (amount === null || amount <= 0)) throw new Error("Enter the amount, like 24.99");
      if (markup === null) throw new Error("Markup must be a percentage like 15 or 12.5");
      const made = await api<Expense>("/expenses", {
        method: "POST",
        json: {
          kind: f.kind,
          expense_date: f.date,
          category_id: f.category_id ? Number(f.category_id) : null,
          description: f.description,
          amount_cents: f.kind === "expense" ? amount : null,
          miles: f.kind === "mileage" ? f.miles : null,
          reimbursable: f.reimbursable,
          billable: f.billable,
          taxable: f.billable && f.taxable,
          markup_bp: f.billable ? markup : 0,
          organization_id: f.organization_id ? Number(f.organization_id) : null,
        },
      });
      if (file) {
        try {
          await api(`/expenses/${made.id}/receipts?filename=${encodeURIComponent(file.name)}`, { method: "POST", body: file, headers: { "Content-Type": file.type } });
        } catch (e) {
          setProblem(`The expense was saved, but the receipt was not: ${(e as Error).message}`);
        }
      }
    },
    onSuccess: () => { setF({ ...blank(), date: f.date }); setFile(null); refresh(); },
    onMutate: () => setProblem(null),
  });
  const voidIt = useMutation({ mutationFn: (id: number) => api(`/expenses/${id}/void`, { method: "POST" }), onSuccess: refresh });

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold tracking-tight">My expenses</h1>
      <Card title="Add an expense">
        <form className="grid gap-3 sm:grid-cols-3" onSubmit={(e) => { e.preventDefault(); add.mutate(); }}>
          <Field label="Type">
            <select className={inputCls} value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value as "expense" | "mileage" })}>
              <option value="expense">Expense (receipt)</option>
              <option value="mileage">Mileage</option>
            </select>
          </Field>
          <Field label="Date"><input className={inputCls} type="date" required value={f.date} onChange={(e) => setF({ ...f, date: e.target.value })} /></Field>
          {f.kind === "expense" ? (
            <Field label="Amount ($)"><input className={inputCls} required inputMode="decimal" value={f.amount} onChange={(e) => setF({ ...f, amount: e.target.value })} /></Field>
          ) : (
            <Field label="Miles"><input className={inputCls} required inputMode="decimal" value={f.miles} onChange={(e) => setF({ ...f, miles: e.target.value })} /></Field>
          )}
          {f.kind === "expense" && (
            <Field label="Category">
              <select className={inputCls} required value={f.category_id} onChange={(e) => setF({ ...f, category_id: e.target.value })}>
                <option value="">Select…</option>
                {cats.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </Field>
          )}
          <div className={f.kind === "expense" ? "sm:col-span-2" : "sm:col-span-3"}><Field label="Description"><input className={inputCls} required value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></Field></div>
          <Field label="Client (optional)">
            <select className={inputCls} value={f.organization_id} onChange={(e) => setF({ ...f, organization_id: e.target.value })}>
              <option value="">None</option>
              {orgList.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
            </select>
          </Field>
          <div className="flex flex-wrap items-end gap-4 pb-2 text-sm sm:col-span-2">
            <label className="flex items-center gap-1"><input type="checkbox" checked={f.reimbursable} onChange={(e) => setF({ ...f, reimbursable: e.target.checked })} />Reimburse me</label>
            <label className="flex items-center gap-1"><input type="checkbox" checked={f.billable} disabled={!f.organization_id} onChange={(e) => setF({ ...f, billable: e.target.checked })} />Bill to client</label>
            {f.billable && (
              <>
                <label className="flex items-center gap-1"><input type="checkbox" checked={f.taxable} onChange={(e) => setF({ ...f, taxable: e.target.checked })} />Taxable</label>
                <label className="flex items-center gap-1">Markup %<input aria-label="Markup %" className={`${inputCls} w-20`} inputMode="decimal" value={f.markup} onChange={(e) => setF({ ...f, markup: e.target.value })} /></label>
              </>
            )}
          </div>
          <Field label="Receipt (PDF, PNG, JPEG or WebP, up to 10 MB)"><input className={inputCls} type="file" accept="application/pdf,image/png,image/jpeg,image/webp" onChange={(e) => setFile(e.target.files?.[0] ?? null)} /></Field>
          <div className="flex items-end"><Button type="submit" disabled={add.isPending}>Add expense</Button></div>
        </form>
        <ErrorMsg error={add.error} />
        {problem && <p role="alert" className="mt-2 text-sm text-amber-800">{problem}</p>}
      </Card>
      <Card title="Entered">
        <ErrorMsg error={list.error ?? voidIt.error} />
        <table className="w-full text-left text-sm">
          <thead className="text-slate-500"><tr><th>Date</th><th>What</th><th>Client</th><th>Cost</th><th>Billed</th><th>Receipts</th><th /></tr></thead>
          <tbody>
            {list.data?.map((e) => (
              <tr key={e.id} className="border-t border-slate-100">
                <td>{e.expense_date}</td>
                <td>{e.kind === "mileage" ? `Mileage: ${e.miles} mi` : e.category_name}: {e.description}{e.reimbursable && <span className="ml-1 text-xs text-slate-500">(reimburse)</span>}</td>
                <td>{e.organization_name ?? "—"}</td>
                <td className="tabular-nums">{money(e.amount_cents)}</td>
                <td className="tabular-nums">{e.billable ? <>{money(e.client_price_cents)}{e.markup_bp > 0 && <span className="text-xs text-slate-500"> (+{percent(e.markup_bp)})</span>}{e.invoiced && " · invoiced"}</> : "—"}</td>
                <td>{e.receipts.map((r) => <a key={r.id} className="mr-2 text-blue-700 hover:underline" href={`/api/expense-receipts/${r.id}/download`}>{r.filename}</a>)}</td>
                <td>{!e.invoiced && <button className="text-red-700 hover:underline" onClick={() => voidIt.mutate(e.id)}>Void</button>}</td>
              </tr>
            ))}
            {list.data?.length === 0 && <tr><td colSpan={7} className="text-slate-500">No expenses yet.</td></tr>}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
