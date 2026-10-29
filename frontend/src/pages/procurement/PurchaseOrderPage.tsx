import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { PoLine, PurchaseOrder, bpPercent, procurement } from "../../api";
import { can, useMe } from "../../auth";
import { money } from "../../money";
import { Button, Card, ErrorMsg, Field, inputCls } from "../../ui";
import { PO_STATUS_LABEL, ProcurementNav } from "./PurchaseOrders";

export default function PurchaseOrderPage() {
  const id = useParams().id as string;
  const { data: me } = useMe();
  const write = can(me, "procurement:write");
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["procurement", "po", id], queryFn: () => procurement.purchaseOrder(id) });
  const [receiving, setReceiving] = useState<PoLine | null>(null);
  const triggerRef = useRef<HTMLElement | null>(null);
  const prevReceiving = useRef<PoLine | null>(null);
  // Return focus to the Receive button that opened the dialog (or the heading if it is gone).
  useEffect(() => {
    if (prevReceiving.current && !receiving) {
      const el = triggerRef.current;
      (el && el.isConnected ? el : headingRef.current)?.focus();
    }
    prevReceiving.current = receiving;
  }, [receiving]);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const done = (po: PurchaseOrder) => {
    qc.setQueryData(["procurement", "po", id], po);
    qc.invalidateQueries({ queryKey: ["procurement"], predicate: (x) => x.queryKey[1] !== "po" });
  };
  const order = useMutation({ mutationFn: () => procurement.order(Number(id)), onSuccess: done });
  const cancel = useMutation({ mutationFn: () => procurement.cancel(Number(id)), onSuccess: done });
  const removeLine = useMutation({
    mutationFn: (line: number) => procurement.deleteLine(Number(id), line),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["procurement"] }),
  });
  const po = q.data;
  if (q.isLoading) return <p>Loading…</p>;
  if (!po) return <ErrorMsg error={q.error ?? "Not found"} />;
  const canReceive = write && (po.status === "ordered" || po.status === "partial");
  const total = po.lines.reduce((t, l) => t + l.quantity * l.unit_cost_cents, 0);
  return (
    <div className="space-y-4">
      <ProcurementNav />
      <p><Link className="text-sm text-blue-700 hover:underline" to="/procurement">← Purchase orders</Link></p>
      <div className="flex flex-wrap items-center gap-2">
        <h2 ref={headingRef} tabIndex={-1} className="text-2xl font-bold tracking-tight outline-none">{po.number ?? `Draft #${po.id}`}</h2>
        <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-700">{PO_STATUS_LABEL[po.status]}</span>
        {write && po.status === "draft" && <Button disabled={order.isPending || po.lines.length === 0} onClick={() => order.mutate()}>Order</Button>}
        {write && (po.status === "draft" || po.status === "ordered") && (
          <Button variant="danger" disabled={cancel.isPending} onClick={() => { if (window.confirm("Cancel this purchase order?")) cancel.mutate(); }}>Cancel order</Button>
        )}
      </div>
      <ErrorMsg error={order.error ?? cancel.error ?? removeLine.error} />
      <Card title="Details">
        <dl className="grid gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
          <dt className="text-slate-500">Vendor</dt><dd>{po.vendor_name ?? "—"}</dd>
          <dt className="text-slate-500">Client</dt>
          <dd>{po.organization_id ? <Link className="text-blue-700 hover:underline" to={`/organizations/${po.organization_id}`}>Client #{po.organization_id}</Link> : "General stock"}</dd>
          <dt className="text-slate-500">Ordered on</dt><dd>{po.ordered_on ?? "—"}</dd>
          <dt className="text-slate-500">Expected on</dt><dd>{po.expected_on ?? "—"}</dd>
          <dt className="text-slate-500">Vendor reference</dt><dd>{po.vendor_reference ?? "—"}</dd>
          <dt className="text-slate-500">Total cost</dt><dd>{money(total)}</dd>
          {po.notes && <><dt className="text-slate-500">Notes</dt><dd>{po.notes}</dd></>}
        </dl>
      </Card>
      {write && receiving && (
        <ReceiveDialog key={receiving.id} poId={po.id} line={receiving} onClose={() => setReceiving(null)} onDone={() => { setReceiving(null); qc.invalidateQueries({ queryKey: ["procurement"] }); }} />
      )}
      <Card title="Lines">
        {po.lines.length === 0 && <p className="text-sm text-slate-500">This order has no lines.</p>}
        {po.lines.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <caption className="sr-only">Purchase order lines</caption>
              <thead>
                <tr className="border-b border-slate-200 text-left text-slate-500">
                  <th scope="col" className="py-1.5">Description</th><th scope="col">Received / ordered</th>
                  <th scope="col" className="text-right">Unit cost</th><th scope="col">Markup</th><th scope="col">Flags</th>
                  <th scope="col"><span className="sr-only">Actions</span></th>
                </tr>
              </thead>
              <tbody>
                {po.lines.map((l) => (
                  <tr key={l.id} className="border-b border-slate-100 align-top">
                    <td className="py-1.5">{l.description}</td>
                    <td>{l.received_quantity} / {l.quantity}</td>
                    <td className="text-right">{money(l.unit_cost_cents)}</td>
                    <td>{l.markup_bp === null ? "Rules" : bpPercent(l.markup_bp)}</td>
                    <td className="text-xs text-slate-600">{[l.serialised && "serialised", l.billable ? "billable" : "not billable", l.taxable && "taxable"].filter(Boolean).join(", ")}</td>
                    <td className="text-right">
                      <span className="flex justify-end gap-2">
                        {canReceive && l.received_quantity < l.quantity && (
                          <Button variant="secondary" aria-label={`Receive ${l.description}`} onClick={(e) => { triggerRef.current = e.currentTarget; setReceiving(l); }}>Receive</Button>
                        )}
                        {write && po.status === "draft" && (
                          <Button variant="danger" aria-label={`Remove ${l.description}`} disabled={removeLine.isPending} onClick={() => removeLine.mutate(l.id)}>Remove</Button>
                        )}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}

function ReceiveDialog({ poId, line, onClose, onDone }: { poId: number; line: PoLine; onClose: () => void; onDone: () => void }) {
  const remaining = line.quantity - line.received_quantity;
  const [qtyText, setQtyText] = useState(String(remaining));
  const [serials, setSerials] = useState<string[]>([]);
  const [bad, setBad] = useState("");
  const [badField, setBadField] = useState<"qty" | number | null>(null);
  const ref = useRef<HTMLElement>(null);
  const qtyRef = useRef<HTMLInputElement>(null);
  const serialRefs = useRef<(HTMLInputElement | null)[]>([]);
  useEffect(() => { qtyRef.current?.focus(); }, []);
  const n = Number(qtyText);
  const validQty = Number.isInteger(n) && n >= 1 && n <= remaining;
  const units = line.serialised && validQty ? n : 0;
  const receive = useMutation({
    mutationFn: (json: { line_id: number; quantity: number; serials: string[] }) => procurement.receive(poId, json),
    onSuccess: onDone,
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!validQty) { setBadField("qty"); qtyRef.current?.focus(); return setBad(`Quantity must be a whole number from 1 to ${remaining}.`); }
    const list = line.serialised ? Array.from({ length: n }, (_, i) => (serials[i] ?? "").trim()) : [];
    const missing = list.findIndex((s) => !s);
    if (line.serialised && missing >= 0) { setBadField(missing); serialRefs.current[missing]?.focus(); return setBad(`Enter ${n} serial number${n === 1 ? "" : "s"}, one per unit.`); }
    setBadField(null);
    setBad("");
    receive.mutate({ line_id: line.id, quantity: n, serials: list });
  };
  return (
    <section ref={ref} role="dialog" aria-modal="true" aria-label={`Receive ${line.description}`} onKeyDown={(e) => { if (e.key === "Escape") onClose(); }} className="rounded-xl border border-blue-300 bg-surface p-5 shadow-card">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="font-semibold">Receive {line.description}</h2>
        <Button variant="secondary" onClick={onClose}>Close</Button>
      </div>
      <form onSubmit={submit} className="space-y-3">
        <div className="max-w-xs">
          <Field label="Quantity received"><input ref={qtyRef} className={inputCls} type="number" min={1} max={remaining} aria-invalid={badField === "qty" || undefined} aria-describedby={badField === "qty" ? "receive-error" : undefined} value={qtyText} onChange={(e) => setQtyText(e.target.value)} /></Field>
        </div>
        {units > 0 && (
          <div className="grid gap-2 sm:grid-cols-3">
            {Array.from({ length: units }, (_, i) => (
              <Field key={i} label={`Serial number ${i + 1}`}>
                <input ref={(el) => { serialRefs.current[i] = el; }} className={inputCls} aria-invalid={badField === i || undefined} aria-describedby={badField === i ? "receive-error" : undefined} value={serials[i] ?? ""} onChange={(e) => { const next = [...serials]; next[i] = e.target.value; setSerials(next); }} />
              </Field>
            ))}
          </div>
        )}
        {bad && <p id="receive-error" role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{bad}</p>}
        <ErrorMsg error={receive.error} />
        <Button type="submit" disabled={receive.isPending}>Receive stock</Button>
      </form>
    </section>
  );
}
