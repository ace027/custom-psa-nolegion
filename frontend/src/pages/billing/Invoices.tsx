import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { InvoiceDetail, InvoiceLine, Invoice, Organization, Page, api } from "../../api";
import { can, useMe } from "../../auth";
import { money, parseMoney, parsePercent, percent, qty } from "../../money";
import { Button, Card, ErrorMsg, Field, fmt, inputCls } from "../../ui";
import { StatusPill } from "./Runs";

const PAY_STYLE: Record<string, string> = {
  paid: "bg-green-100 text-green-800", partial: "bg-blue-100 text-blue-800", unpaid: "bg-slate-100 text-slate-700", written_off: "bg-slate-100 text-slate-500",
};
export function PayPill({ inv }: { inv: Invoice }) {
  if (!inv.payment_status) return null;
  return (
    <span className="flex items-center gap-1">
      <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${PAY_STYLE[inv.payment_status]}`}>{inv.payment_status.replace("_", " ")}</span>
      {inv.is_overdue && <span className="rounded bg-red-100 px-1.5 py-0.5 text-xs font-medium text-red-800">{inv.days_past_due}d overdue</span>}
    </span>
  );
}

export function InvoiceList() {
  const { data: me } = useMe();
  const nav = useNavigate();
  const [sp] = useSearchParams();
  const [status, setStatus] = useState("");
  const [pay, setPay] = useState(sp.get("pay") ?? "");
  const filterOrg = sp.get("org");
  const [orgId, setOrgId] = useState("");
  const orgs = useQuery({ queryKey: ["orgs", "", false], queryFn: () => api<Page<Organization>>("/organizations?limit=200&include_archived=false&q=") });
  const list = useQuery({
    queryKey: ["invoices", status, pay, filterOrg],
    queryFn: () => api<Page<Invoice>>(`/invoices?limit=100${status ? `&status=${status}` : ""}${pay ? `&payment_status=${pay}` : ""}${filterOrg ? `&organization_id=${filterOrg}` : ""}`),
  });
  const create = useMutation({
    mutationFn: () => api<InvoiceDetail>("/invoices", { method: "POST", json: { organization_id: Number(orgId) } }),
    onSuccess: (i) => nav(`/billing/invoices/${i.id}`),
  });
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <Field label="Status">
          <select className={inputCls} value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">Any</option><option value="draft">Draft</option><option value="final">Final</option><option value="void">Void</option>
          </select>
        </Field>
        <Field label="Payment">
          <select className={inputCls} value={pay} onChange={(e) => setPay(e.target.value)}>
            <option value="">Any</option><option value="open">Owes money</option><option value="overdue">Overdue</option><option value="unpaid">Nothing paid</option><option value="paid">Paid</option>
          </select>
        </Field>
        {can(me, "billing:write") && (
          <form className="flex items-end gap-2" onSubmit={(e) => { e.preventDefault(); create.mutate(); }}>
            <Field label="New one-off invoice for">
              <select className={inputCls} required value={orgId} onChange={(e) => setOrgId(e.target.value)}>
                <option value="">Select client…</option>
                {orgs.data?.items.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
              </select>
            </Field>
            <Button type="submit">Create draft</Button>
          </form>
        )}
      </div>
      <ErrorMsg error={create.error ?? list.error} />
      <table className="w-full rounded-lg border border-slate-200 bg-surface text-left text-sm">
        <thead className="border-b border-slate-200 text-slate-500"><tr><th className="p-2">Number</th><th>Client</th><th>Status</th><th>Date</th><th>Due</th><th className="text-right">Total</th><th className="text-right">Balance</th><th>Payment</th></tr></thead>
        <tbody>
          {list.data?.items.map((i) => (
            <tr key={i.id} className="border-b border-slate-100">
              <td className="p-2"><Link className="font-medium text-blue-700 hover:underline" to={`/billing/invoices/${i.id}`}>{i.number ?? `draft #${i.id}`}</Link></td>
              <td>{i.organization_name}</td><td><StatusPill status={i.status} /></td>
              <td>{i.invoice_date ?? ""}</td><td>{i.due_date ?? ""}</td><td className="text-right">{money(i.total_cents)}</td>
              <td className="text-right">{i.balance_cents === null ? "" : i.balance_cents === 0 ? "–" : money(i.balance_cents)}</td>
              <td><PayPill inv={i} /></td>
            </tr>
          ))}
          {list.data?.items.length === 0 && <tr><td colSpan={8} className="p-3 text-slate-500">No invoices.</td></tr>}
        </tbody>
      </table>
    </div>
  );
}

export function InvoicePage() {
  const id = Number(useParams().id);
  const { data: me } = useMe();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["invoice", id], queryFn: () => api<InvoiceDetail>(`/invoices/${id}`) });
  const refresh = () => qc.invalidateQueries();
  const act = useMutation({
    mutationFn: ({ path, json }: { path: string; json?: object }) => api<InvoiceDetail>(`/invoices/${id}/${path}`, { method: "POST", json }),
    onSuccess: refresh,
  });
  const inv = q.data;
  if (!inv) return <ErrorMsg error={q.error ?? "Loading…"} />;
  const draft = inv.status === "draft";
  const canEdit = draft && can(me, "billing:write");
  const canFinalize = can(me, "billing:finalize");
  const inOpenRun = inv.billing_run_id !== null && draft;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-lg font-semibold">{inv.number ?? `Draft invoice #${inv.id}`}</h2>
        <StatusPill status={inv.status} />
        <span className="text-slate-600">{inv.organization_name}</span>
        <a className="ml-auto text-sm text-blue-700 hover:underline" href={`/api/invoices/${inv.id}/pdf`}>Download PDF</a>
        {inv.status === "final" && can(me, "billing:write") && <EmailInvoice id={inv.id} />}
        {inv.billing_run_id && <Link className="text-sm text-blue-700 hover:underline" to={`/billing/runs/${inv.billing_run_id}`}>Billing run</Link>}
      </div>
      {inv.warnings.length > 0 && <Card title="Warnings"><ul className="list-disc pl-5 text-sm text-amber-800">{inv.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul></Card>}
      {inv.status === "void" && <p className="rounded bg-slate-100 p-2 text-sm">Voided{inv.void_reason ? `: ${inv.void_reason}` : ""}. Its number is kept and never reused.</p>}
      {inv.status === "final" && <PaymentSection inv={inv} canRecord={can(me, "payment:write")} canVoid={canFinalize} onDone={refresh} />}
      {!draft && <p className="text-sm text-slate-600">Invoice date {inv.invoice_date} · Due {inv.due_date} (Net {inv.terms_days}). This invoice is frozen.</p>}
      <ErrorMsg error={act.error} />
      <table className="w-full rounded-lg border border-slate-200 bg-surface text-left text-sm">
        <thead className="border-b border-slate-200 text-slate-500"><tr><th className="p-2">Description</th><th className="text-right">Qty</th><th className="text-right">Unit price</th><th className="text-right">Amount</th><th className="text-right">Tax</th>{canEdit && <th />}</tr></thead>
        <tbody>{inv.lines.map((l) => <LineRow key={l.id} line={l} editable={canEdit} onDone={refresh} />)}</tbody>
        <tfoot className="text-sm">
          <tr><td colSpan={3} className="p-2 text-right text-slate-500">Subtotal</td><td className="text-right">{money(inv.subtotal_cents)}</td><td /></tr>
          <tr><td colSpan={3} className="p-2 text-right text-slate-500">Tax</td><td className="text-right">{money(inv.tax_cents)}</td><td /></tr>
          <tr className="font-semibold"><td colSpan={3} className="p-2 text-right">Total</td><td className="text-right">{money(inv.total_cents)}</td><td /></tr>
        </tfoot>
      </table>
      {canEdit && <AddLine invoiceId={inv.id} onDone={refresh} />}
      <div className="flex flex-wrap gap-2">
        {canEdit && <Button variant="secondary" onClick={() => act.mutate({ path: "add-unbilled" })}>Add unbilled time and charges</Button>}
        {draft && canFinalize && !inOpenRun && (
          <Button onClick={() => { if (window.confirm("Finalize this invoice? It will be numbered and can no longer be edited.")) act.mutate({ path: "finalize", json: {} }); }}>Finalize invoice</Button>
        )}
        {inOpenRun && <span className="text-sm text-slate-500">This draft is part of a billing run: finalize it from the run.</span>}
        {inv.status !== "void" && canFinalize && (
          <Button variant="danger" onClick={() => {
            const reason = draft ? "" : window.prompt("Reason for voiding this finalized invoice (required):");
            if (draft ? window.confirm("Discard this draft?") : reason) act.mutate({ path: "void", json: { reason } });
          }}>{draft ? "Discard draft" : "Void invoice"}</Button>
        )}
      </div>
      {inv.memo && <p className="whitespace-pre-wrap text-sm"><b>Notes:</b> {inv.memo}</p>}
      <p className="text-xs text-slate-500">Created {fmt(inv.created_at)}.</p>
    </div>
  );
}

function LineRow({ line, editable, onDone }: { line: InvoiceLine; editable: boolean; onDone: () => void }) {
  const [f, setF] = useState({ description: line.description, quantity: qty(line.quantity), price: money(line.unit_price_cents).replace("$", ""), tax: percent(line.tax_rate_bp).replace("%", "") });
  const [err, setErr] = useState<string | null>(null);
  const save = useMutation({
    mutationFn: () => {
      const cents = parseMoney(f.price), bp = parsePercent(f.tax);
      if (cents === null || bp === null) throw new Error("Enter valid amounts");
      return api(`/invoice-lines/${line.id}`, { method: "PATCH", json: { description: f.description, quantity: f.quantity, unit_price_cents: cents, tax_rate_bp: bp } });
    },
    onSuccess: () => { setErr(null); onDone(); },
    onError: (e) => setErr((e as Error).message),
  });
  const del = useMutation({ mutationFn: () => api(`/invoice-lines/${line.id}`, { method: "DELETE" }), onSuccess: onDone });
  if (!editable) {
    return (
      <tr className="border-b border-slate-100 align-top">
        <td className="p-2">{line.description}</td><td className="text-right">{qty(line.quantity)}</td>
        <td className="text-right">{money(line.unit_price_cents)}</td><td className="text-right">{money(line.amount_cents)}</td>
        <td className="text-right">{line.tax_rate_bp ? `${money(line.tax_cents)} (${percent(line.tax_rate_bp)})` : ""}</td>
      </tr>
    );
  }
  return (
    <tr className="border-b border-slate-100 align-top">
      <td className="p-1"><input aria-label="Line description" className={inputCls} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} />{err && <p role="alert" className="text-xs text-red-700">{err}</p>}</td>
      <td className="p-1"><input aria-label="Line quantity" className={inputCls + " w-20 text-right"} value={f.quantity} onChange={(e) => setF({ ...f, quantity: e.target.value })} /></td>
      <td className="p-1"><input aria-label="Line unit price" className={inputCls + " w-24 text-right"} value={f.price} onChange={(e) => setF({ ...f, price: e.target.value })} /></td>
      <td className="p-1 text-right">{money(line.amount_cents)}</td>
      <td className="p-1"><input aria-label="Line tax percent" className={inputCls + " w-16 text-right"} value={f.tax} onChange={(e) => setF({ ...f, tax: e.target.value })} /> %</td>
      <td className="whitespace-nowrap p-1"><Button variant="secondary" onClick={() => save.mutate()}>Save</Button> <button className="text-red-700 hover:underline" onClick={() => del.mutate()}>Remove</button></td>
    </tr>
  );
}

function AddLine({ invoiceId, onDone }: { invoiceId: number; onDone: () => void }) {
  const [f, setF] = useState({ description: "", quantity: "1", price: "", taxable: false });
  const add = useMutation({
    mutationFn: () => {
      const cents = parseMoney(f.price);
      if (cents === null) throw new Error("Enter a valid price, e.g. 125.00 (negative for a credit)");
      return api(`/invoices/${invoiceId}/lines`, { method: "POST", json: { description: f.description, quantity: f.quantity, unit_price_cents: cents, taxable: f.taxable } });
    },
    onSuccess: () => { setF({ description: "", quantity: "1", price: "", taxable: false }); onDone(); },
  });
  return (
    <form className="flex flex-wrap items-end gap-2 rounded-lg border border-slate-200 bg-surface p-3" onSubmit={(e) => { e.preventDefault(); add.mutate(); }}>
      <div className="w-72"><Field label="Add a line (or a credit)"><input className={inputCls} required value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></Field></div>
      <div className="w-20"><Field label="Qty"><input className={inputCls} value={f.quantity} onChange={(e) => setF({ ...f, quantity: e.target.value })} /></Field></div>
      <div className="w-28"><Field label="Unit price ($)"><input className={inputCls} required value={f.price} onChange={(e) => setF({ ...f, price: e.target.value })} /></Field></div>
      <label className="flex items-center gap-1 pb-2 text-sm"><input type="checkbox" checked={f.taxable} onChange={(e) => setF({ ...f, taxable: e.target.checked })} />Taxable</label>
      <Button type="submit">Add line</Button>
      <ErrorMsg error={add.error} />
    </form>
  );
}


function PaymentSection({ inv, canRecord, canVoid, onDone }: { inv: InvoiceDetail; canRecord: boolean; canVoid: boolean; onDone: () => void }) {
  const unapply = useMutation({ mutationFn: ({ id, reason }: { id: number; reason: string }) => api(`/payment-applications/${id}/void`, { method: "POST", json: { reason } }), onSuccess: onDone });
  const writeOff = useMutation({ mutationFn: (reason: string) => api(`/invoices/${inv.id}/write-off`, { method: "POST", json: { reason } }), onSuccess: onDone });
  const voidWo = useMutation({ mutationFn: ({ id, reason }: { id: number; reason: string }) => api(`/write-offs/${id}/void`, { method: "POST", json: { reason } }), onSuccess: onDone });
  const balance = inv.balance_cents ?? 0;
  return (
    <Card title="Payment">
      <div className="flex flex-wrap items-center gap-4 text-sm">
        <PayPill inv={inv} />
        <span>Total <b>{money(inv.total_cents)}</b></span>
        <span>Paid <b>{money(inv.paid_cents ?? 0)}</b></span>
        {(inv.written_off_cents ?? 0) > 0 && <span>Written off <b>{money(inv.written_off_cents ?? 0)}</b></span>}
        <span className={balance > 0 ? "text-base font-semibold" : ""}>Balance <b>{money(balance)}</b></span>
        {canRecord && balance > 0 && <Link className="rounded bg-blue-600 px-3 py-1.5 text-sm font-medium text-on-accent hover:bg-blue-700" to={`/billing/payments?new=1&org=${inv.organization_id}&invoice=${inv.id}`}>Record payment</Link>}
        {canVoid && balance > 0 && <Button variant="secondary" onClick={() => { const r = window.prompt(`Write off the ${money(balance)} balance as uncollectible. Reason (required):`); if (r) writeOff.mutate(r); }}>Write off balance</Button>}
      </div>
      <ErrorMsg error={unapply.error ?? writeOff.error ?? voidWo.error} />
      {(inv.payments.length > 0 || inv.write_offs.length > 0) && (
        <ul className="mt-3 space-y-1 text-sm">
          {inv.payments.map((p) => (
            <li key={p.application_id} className={p.voided_at ? "text-slate-400 line-through" : ""}>
              {money(p.amount_cents)} · {p.received_on} · {p.method}{p.reference ? ` #${p.reference}` : ""}{p.voided_at ? ` (undone: ${p.void_reason})` : ""}
              {!p.voided_at && canVoid && <button className="ml-2 text-red-700 hover:underline" onClick={() => { const r = window.prompt("Reason for undoing this payment application:"); if (r) unapply.mutate({ id: p.application_id, reason: r }); }}>undo</button>}
            </li>
          ))}
          {inv.write_offs.map((w) => (
            <li key={`w${w.id}`} className={w.voided_at ? "text-slate-400 line-through" : ""}>
              {money(w.amount_cents)} written off: {w.reason}{w.voided_at ? ` (reversed: ${w.void_reason})` : ""}
              {!w.voided_at && canVoid && <button className="ml-2 text-red-700 hover:underline" onClick={() => { const r = window.prompt("Reason for reversing this write-off:"); if (r) voidWo.mutate({ id: w.id, reason: r }); }}>reverse</button>}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function EmailInvoice({ id }: { id: number }) {
  const nav = useNavigate();
  const qc = useQueryClient();
  const prepare = useMutation({
    mutationFn: () => api(`/invoices/${id}/email`, { method: "POST" }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["notices"] }); nav("/billing/reminders"); },
  });
  return (
    <>
      <Button variant="secondary" onClick={() => prepare.mutate()}>Prepare email to client</Button>
      <ErrorMsg error={prepare.error} />
    </>
  );
}
