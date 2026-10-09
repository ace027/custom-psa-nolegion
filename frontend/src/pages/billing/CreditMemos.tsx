import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { CreditMemo, CreditMemoDetail, Invoice, Organization, Page, api } from "../../api";
import { can, useMe } from "../../auth";
import { money, parseMoney } from "../../money";
import { Button, ErrorMsg, Field, fmt, inputCls } from "../../ui";

const blankLine = { description: "", quantity: "1", price: "", taxable: false };

export default function CreditMemos() {
  const { data: me } = useMe();
  const canIssue = can(me, "billing:finalize");
  const list = useQuery({ queryKey: ["credit-memos"], queryFn: () => api<Page<CreditMemo>>("/credit-memos?limit=100") });
  return (
    <div className="space-y-4">
      <p className="text-sm text-slate-600">A credit memo is a numbered, permanent credit to a client, used to correct an invoice after it was finalized. Apply it to open invoices; whatever is not applied stays as <b>credit on the client&apos;s account</b>. Memos are never edited: void one (with a reason) and issue a new one.</p>
      {canIssue && <IssueMemo />}
      <ErrorMsg error={list.error} />
      <table className="w-full rounded-lg border border-slate-200 bg-surface text-left text-sm">
        <thead className="border-b border-slate-200 text-slate-500"><tr><th className="p-2">Number</th><th>Date</th><th>Client</th><th>Reason</th><th className="text-right">Total</th><th className="text-right">Unapplied</th><th /></tr></thead>
        <tbody>
          {list.data?.items.map((m) => <MemoRow key={m.id} m={m} />)}
          {list.data?.items.length === 0 && <tr><td colSpan={7} className="p-3 text-slate-500">No credit memos.</td></tr>}
        </tbody>
      </table>
    </div>
  );
}

function IssueMemo() {
  const qc = useQueryClient();
  const orgs = useQuery({ queryKey: ["orgs", "", false], queryFn: () => api<Page<Organization>>("/organizations?limit=200&include_archived=false&q=") });
  const [orgId, setOrgId] = useState("");
  const [reason, setReason] = useState("");
  const [lines, setLines] = useState([{ ...blankLine }]);
  const [invoiceId, setInvoiceId] = useState("");
  const open = useQuery({
    queryKey: ["open-invoices", orgId],
    enabled: !!orgId,
    queryFn: () => api<Page<Invoice>>(`/invoices?organization_id=${orgId}&payment_status=open&limit=200`),
  });
  const setLine = (i: number, patch: Partial<typeof blankLine>) => setLines(lines.map((l, j) => (j === i ? { ...l, ...patch } : l)));
  const issue = useMutation({
    mutationFn: () => {
      if (!orgId) throw new Error("Choose a client");
      const parsed = lines.map((l) => ({ description: l.description, quantity: l.quantity, unit_price_cents: parseMoney(l.price), taxable: l.taxable }));
      if (parsed.some((l) => !l.description || !l.unit_price_cents || l.unit_price_cents <= 0)) throw new Error("Every line needs a description and a positive price");
      return api("/credit-memos", { method: "POST", json: { organization_id: Number(orgId), reason, lines: parsed, invoice_id: invoiceId ? Number(invoiceId) : null } });
    },
    onSuccess: () => { setReason(""); setLines([{ ...blankLine }]); setInvoiceId(""); qc.invalidateQueries(); },
  });
  return (
    <form className="space-y-3 rounded-lg border border-slate-200 bg-surface p-4" onSubmit={(e) => { e.preventDefault(); issue.mutate(); }}>
      <h2 className="font-semibold">Issue a credit memo</h2>
      <div className="grid gap-3 sm:grid-cols-3">
        <Field label="Client"><select className={inputCls} required value={orgId} onChange={(e) => { setOrgId(e.target.value); setInvoiceId(""); }}><option value="">Select…</option>{orgs.data?.items.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}</select></Field>
        <Field label="Reason (shown on the memo)"><input className={inputCls} required minLength={3} value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
        <Field label="Corrects invoice (optional)"><select className={inputCls} value={invoiceId} onChange={(e) => setInvoiceId(e.target.value)}><option value="">None</option>{open.data?.items.map((i) => <option key={i.id} value={i.id}>{i.number}</option>)}</select></Field>
      </div>
      {lines.map((l, i) => (
        <div key={i} className="grid gap-2 sm:grid-cols-6">
          <div className="sm:col-span-3"><Field label={`Line ${i + 1} description`}><input className={inputCls} value={l.description} onChange={(e) => setLine(i, { description: e.target.value })} /></Field></div>
          <Field label="Quantity"><input className={inputCls} value={l.quantity} onChange={(e) => setLine(i, { quantity: e.target.value })} /></Field>
          <Field label="Unit price ($)"><input className={inputCls} value={l.price} onChange={(e) => setLine(i, { price: e.target.value })} /></Field>
          <label className="flex items-end gap-1 pb-2 text-sm"><input type="checkbox" checked={l.taxable} onChange={(e) => setLine(i, { taxable: e.target.checked })} />Taxable</label>
        </div>
      ))}
      <div className="flex gap-2"><Button type="button" variant="secondary" onClick={() => setLines([...lines, { ...blankLine }])}>Add line</Button></div>
      <p className="text-xs text-slate-500">Amounts are positive; the memo reduces what the client owes. Tax uses the client&apos;s rate on taxable lines.</p>
      <ErrorMsg error={issue.error} />
      <Button type="submit" disabled={issue.isPending}>Issue credit memo</Button>
    </form>
  );
}

function MemoRow({ m }: { m: CreditMemo }) {
  const { data: me } = useMe();
  const qc = useQueryClient();
  const [show, setShow] = useState(false);
  const detail = useQuery({ queryKey: ["credit-memo", m.id], enabled: show, queryFn: () => api<CreditMemoDetail>(`/credit-memos/${m.id}`) });
  const [target, setTarget] = useState({ invoice_id: "", amount: "" });
  const open = useQuery({ queryKey: ["open-invoices", String(m.organization_id)], enabled: show && m.unapplied_cents > 0, queryFn: () => api<Page<Invoice>>(`/invoices?organization_id=${m.organization_id}&payment_status=open&limit=200`) });
  const refresh = () => qc.invalidateQueries();
  const apply = useMutation({
    mutationFn: () => { const c = parseMoney(target.amount); if (!c) throw new Error("Enter an amount"); return api(`/credit-memos/${m.id}/apply`, { method: "POST", json: { invoice_id: Number(target.invoice_id), amount_cents: c } }); },
    onSuccess: () => { setTarget({ invoice_id: "", amount: "" }); refresh(); },
  });
  const voidMemo = useMutation({ mutationFn: (reason: string) => api(`/credit-memos/${m.id}/void`, { method: "POST", json: { reason } }), onSuccess: refresh });
  const unapply = useMutation({ mutationFn: (v: { id: number; reason: string }) => api(`/credit-memo-applications/${v.id}/void`, { method: "POST", json: { reason: v.reason } }), onSuccess: refresh });
  return (
    <>
      <tr className={`border-b border-slate-100 ${m.status === "void" ? "text-slate-400 line-through" : ""}`}>
        <td className="p-2 font-medium">{m.number}</td><td>{m.memo_date}</td><td>{m.organization_name}</td><td>{m.reason}</td>
        <td className="text-right">{money(m.total_cents)}</td><td className="text-right">{m.unapplied_cents ? money(m.unapplied_cents) : "–"}</td>
        <td><button className="text-blue-700 hover:underline" onClick={() => setShow(!show)}>{show ? "hide" : "details"}</button></td>
      </tr>
      {show && (
        <tr><td colSpan={7} className="space-y-2 bg-slate-50 p-3 text-sm">
          {m.status === "void" && <p>Voided: {m.void_reason}</p>}
          {detail.data?.lines.map((l) => <div key={l.position}>{l.description}: {l.quantity} × {money(l.unit_price_cents)} = {money(l.amount_cents)}{l.tax_cents ? ` + tax ${money(l.tax_cents)}` : ""}</div>)}
          {detail.data?.applications.map((a) => (
            <div key={a.id} className={a.voided_at ? "text-slate-400 line-through" : ""}>
              {money(a.amount_cents)} applied to invoice #{a.invoice_id}{a.voided_at ? ` (undone: ${a.void_reason})` : ""}
              {!a.voided_at && can(me, "billing:finalize") && <button className="ml-2 text-red-700 hover:underline" onClick={() => { const why = window.prompt("Reason for undoing this application:"); if (why) unapply.mutate({ id: a.id, reason: why }); }}>undo</button>}
            </div>
          ))}
          {m.status === "active" && can(me, "payment:write") && m.unapplied_cents > 0 && (
            <div className="flex flex-wrap items-end gap-2">
              <Field label={`Apply credit (${money(m.unapplied_cents)} available)`}>
                <select className={inputCls} value={target.invoice_id} onChange={(e) => { const i = open.data?.items.find((x) => String(x.id) === e.target.value); setTarget({ invoice_id: e.target.value, amount: i ? (Math.min(i.balance_cents ?? 0, m.unapplied_cents) / 100).toFixed(2) : "" }); }}>
                  <option value="">Choose an invoice…</option>{open.data?.items.map((i) => <option key={i.id} value={i.id}>{i.number} (owes {money(i.balance_cents ?? 0)})</option>)}
                </select>
              </Field>
              <div className="w-28"><Field label="Amount ($)"><input className={inputCls} value={target.amount} onChange={(e) => setTarget({ ...target, amount: e.target.value })} /></Field></div>
              <Button disabled={!target.invoice_id} onClick={() => apply.mutate()}>Apply</Button>
            </div>
          )}
          <ErrorMsg error={apply.error ?? voidMemo.error ?? unapply.error} />
          {m.status === "active" && can(me, "billing:finalize") && (
            <Button variant="danger" onClick={() => { const r = window.prompt("Reason for voiding this credit memo:"); if (r) voidMemo.mutate(r); }}>Void credit memo</Button>
          )}
          <p className="text-xs text-slate-400">Issued {fmt(m.created_at)}</p>
        </td></tr>
      )}
    </>
  );
}
