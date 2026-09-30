import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Invoice, METHODS, Organization, Page, Payment, PaymentDetail, PaymentMethod, api } from "../../api";
import { can, useMe } from "../../auth";
import { money, parseMoney } from "../../money";
import { Button, ErrorMsg, Field, fmt, inputCls } from "../../ui";

export default function Payments() {
  const { data: me } = useMe();
  const [params] = useSearchParams();
  const canWrite = can(me, "payment:write");
  const list = useQuery({ queryKey: ["payments"], queryFn: () => api<Page<Payment>>("/payments?limit=100") });
  return (
    <div className="space-y-4">
      <p className="text-sm text-slate-600">Record money received. Split one payment across several invoices, or leave part of it as <b>credit</b> to apply later. Payments are never edited: if one was entered wrong, void it (with a reason) and record it again.</p>
      {canWrite && <RecordPayment initialOrg={params.get("org") ?? ""} initialInvoice={params.get("invoice") ?? ""} />}
      <ErrorMsg error={list.error} />
      <table className="w-full rounded-lg border border-slate-200 bg-white text-left text-sm">
        <thead className="border-b border-slate-200 text-slate-500"><tr><th className="p-2">Received</th><th>Client</th><th>Method</th><th>Reference</th><th className="text-right">Amount</th><th className="text-right">Unapplied</th><th /></tr></thead>
        <tbody>{list.data?.items.map((p) => <PaymentRow key={p.id} p={p} />)}
          {list.data?.items.length === 0 && <tr><td colSpan={7} className="p-3 text-slate-500">No payments recorded.</td></tr>}</tbody>
      </table>
    </div>
  );
}

function RecordPayment({ initialOrg, initialInvoice }: { initialOrg: string; initialInvoice: string }) {
  const qc = useQueryClient();
  const orgs = useQuery({ queryKey: ["orgs", "", false], queryFn: () => api<Page<Organization>>("/organizations?limit=200&include_archived=false&q=") });
  const [orgId, setOrgId] = useState(initialOrg);
  const [amount, setAmount] = useState("");
  const [alloc, setAlloc] = useState<Record<number, string>>({});
  const [f, setF] = useState({ received_on: "", method: "check" as PaymentMethod, reference: "", notes: "" });
  const open = useQuery({
    queryKey: ["open-invoices", orgId],
    enabled: !!orgId,
    queryFn: () => api<Page<Invoice>>(`/invoices?organization_id=${orgId}&payment_status=open&limit=200`),
  });
  const invoices = [...(open.data?.items ?? [])].sort((a, b) => (a.due_date ?? "").localeCompare(b.due_date ?? ""));
  const cents = parseMoney(amount);
  const applied = invoices.reduce((s, i) => s + (parseMoney(alloc[i.id] ?? "") ?? 0), 0);
  const remaining = (cents ?? 0) - applied;
  const autoApply = () => {
    let left = cents ?? 0;
    const next: Record<number, string> = {};
    for (const i of invoices) {
      const take = Math.min(left, i.balance_cents ?? 0);
      if (take > 0) next[i.id] = (take / 100).toFixed(2);
      left -= take;
    }
    setAlloc(next);
  };
  const save = useMutation({
    mutationFn: () => {
      if (!orgId || !cents || cents <= 0) throw new Error("Choose a client and enter the amount received");
      if (remaining < 0) throw new Error("You applied more than the payment amount");
      const applications = invoices.flatMap((i) => {
        const c = parseMoney(alloc[i.id] ?? "");
        return c && c > 0 ? [{ invoice_id: i.id, amount_cents: c }] : [];
      });
      return api("/payments", { method: "POST", json: { organization_id: Number(orgId), amount_cents: cents, received_on: f.received_on || null, method: f.method, reference: f.reference || null, notes: f.notes || null, applications } });
    },
    onSuccess: () => {
      setAmount(""); setAlloc({}); setF({ ...f, reference: "", notes: "" });
      qc.invalidateQueries();
    },
  });
  // preselect the invoice we came from, once, when its list has loaded
  const [seeded, setSeeded] = useState(false);
  if (!seeded && initialInvoice && invoices.some((i) => String(i.id) === initialInvoice)) {
    const inv = invoices.find((i) => String(i.id) === initialInvoice)!;
    setSeeded(true);
    setAmount(((inv.balance_cents ?? 0) / 100).toFixed(2));
    setAlloc({ [inv.id]: ((inv.balance_cents ?? 0) / 100).toFixed(2) });
  }
  return (
    <form className="space-y-3 rounded-lg border border-slate-200 bg-white p-4" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
      <h2 className="font-semibold">Record a payment</h2>
      <div className="grid gap-3 sm:grid-cols-5">
        <Field label="Client"><select className={inputCls} required value={orgId} onChange={(e) => { setOrgId(e.target.value); setAlloc({}); }}><option value="">Select…</option>{orgs.data?.items.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}</select></Field>
        <Field label="Amount received ($)"><input className={inputCls} required value={amount} onChange={(e) => setAmount(e.target.value)} /></Field>
        <Field label="Date received (blank = today)"><input className={inputCls} type="date" value={f.received_on} onChange={(e) => setF({ ...f, received_on: e.target.value })} /></Field>
        <Field label="Method"><select className={inputCls} value={f.method} onChange={(e) => setF({ ...f, method: e.target.value as PaymentMethod })}>{METHODS.map((m) => <option key={m}>{m}</option>)}</select></Field>
        <Field label="Reference (check #, ACH id)"><input className={inputCls} value={f.reference} onChange={(e) => setF({ ...f, reference: e.target.value })} /></Field>
      </div>
      {orgId && (
        <div>
          <div className="mb-1 flex items-center gap-3"><b className="text-sm">Apply to invoices</b><Button type="button" variant="secondary" onClick={autoApply}>Auto-apply, oldest first</Button></div>
          <table className="w-full text-left text-sm">
            <thead className="text-slate-500"><tr><th>Invoice</th><th>Due</th><th className="text-right">Balance</th><th className="w-32">Apply ($)</th></tr></thead>
            <tbody>
              {invoices.map((i) => (
                <tr key={i.id} className="border-t border-slate-100">
                  <td className="py-1">{i.number}</td>
                  <td className={i.is_overdue ? "text-red-700" : ""}>{i.due_date}{i.is_overdue ? ` (${i.days_past_due}d late)` : ""}</td>
                  <td className="text-right">{money(i.balance_cents ?? 0)}</td>
                  <td><input aria-label={`Apply to ${i.number}`} className={inputCls} value={alloc[i.id] ?? ""} onChange={(e) => setAlloc({ ...alloc, [i.id]: e.target.value })} /></td>
                </tr>
              ))}
              {invoices.length === 0 && <tr><td colSpan={4} className="text-slate-500">No open invoices for this client. The payment will be kept as credit.</td></tr>}
            </tbody>
          </table>
          {cents !== null && cents > 0 && <p className={`mt-1 text-sm ${remaining < 0 ? "text-red-700" : "text-slate-600"}`}>{remaining < 0 ? `Over-applied by ${money(-remaining)}` : remaining > 0 ? `${money(remaining)} will be kept as credit on the client's account.` : "Fully applied."}</p>}
        </div>
      )}
      <Field label="Notes"><input className={inputCls} value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} /></Field>
      <ErrorMsg error={save.error} />
      <Button type="submit" disabled={save.isPending}>Record payment</Button>
    </form>
  );
}

function PaymentRow({ p }: { p: Payment }) {
  const { data: me } = useMe();
  const qc = useQueryClient();
  const [show, setShow] = useState(false);
  const detail = useQuery({ queryKey: ["payment", p.id], enabled: show, queryFn: () => api<PaymentDetail>(`/payments/${p.id}`) });
  const [target, setTarget] = useState({ invoice_id: "", amount: "" });
  const open = useQuery({ queryKey: ["open-invoices", String(p.organization_id)], enabled: show && p.unapplied_cents > 0, queryFn: () => api<Page<Invoice>>(`/invoices?organization_id=${p.organization_id}&payment_status=open&limit=200`) });
  const refresh = () => qc.invalidateQueries();
  const voidIt = useMutation({ mutationFn: (reason: string) => api(`/payments/${p.id}/void`, { method: "POST", json: { reason } }), onSuccess: refresh });
  const apply = useMutation({
    mutationFn: () => { const c = parseMoney(target.amount); if (!c) throw new Error("Enter an amount"); return api(`/payments/${p.id}/apply`, { method: "POST", json: { invoice_id: Number(target.invoice_id), amount_cents: c } }); },
    onSuccess: () => { setTarget({ invoice_id: "", amount: "" }); refresh(); },
  });
  return (
    <>
      <tr className={`border-b border-slate-100 ${p.status === "void" ? "text-slate-400 line-through" : ""}`}>
        <td className="p-2">{p.received_on}</td><td>{p.organization_name}</td><td>{p.method}</td><td>{p.reference}</td>
        <td className="text-right">{money(p.amount_cents)}</td><td className="text-right">{p.unapplied_cents ? money(p.unapplied_cents) : "–"}</td>
        <td><button className="text-blue-700 hover:underline" onClick={() => setShow(!show)}>{show ? "hide" : "details"}</button></td>
      </tr>
      {show && (
        <tr><td colSpan={7} className="space-y-2 bg-slate-50 p-3 text-sm">
          {p.status === "void" && <p>Voided: {p.void_reason}</p>}
          {detail.data?.applications.map((a) => <div key={a.id} className={a.voided_at ? "text-slate-400 line-through" : ""}>{money(a.amount_cents)} applied to invoice #{a.invoice_id}{a.voided_at ? ` (undone: ${a.void_reason})` : ""}</div>)}
          {p.notes && <div>Notes: {p.notes}</div>}
          {p.status === "active" && can(me, "payment:write") && p.unapplied_cents > 0 && (
            <div className="flex flex-wrap items-end gap-2">
              <Field label={`Apply credit (${money(p.unapplied_cents)} available)`}>
                <select className={inputCls} value={target.invoice_id} onChange={(e) => { const i = open.data?.items.find((x) => String(x.id) === e.target.value); setTarget({ invoice_id: e.target.value, amount: i ? (Math.min(i.balance_cents ?? 0, p.unapplied_cents) / 100).toFixed(2) : "" }); }}>
                  <option value="">Choose an invoice…</option>{open.data?.items.map((i) => <option key={i.id} value={i.id}>{i.number} (owes {money(i.balance_cents ?? 0)})</option>)}
                </select>
              </Field>
              <div className="w-28"><Field label="Amount ($)"><input className={inputCls} value={target.amount} onChange={(e) => setTarget({ ...target, amount: e.target.value })} /></Field></div>
              <Button disabled={!target.invoice_id} onClick={() => apply.mutate()}>Apply</Button>
            </div>
          )}
          <ErrorMsg error={apply.error ?? voidIt.error} />
          {p.status === "active" && can(me, "billing:finalize") && (
            <Button variant="danger" onClick={() => { const r = window.prompt("Reason for voiding this payment (e.g. check bounced):"); if (r) voidIt.mutate(r); }}>Void payment</Button>
          )}
          <p className="text-xs text-slate-400">Recorded {fmt(p.created_at)}</p>
        </td></tr>
      )}
    </>
  );
}
