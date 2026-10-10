import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { LateFeePreview, api } from "../../api";
import { can, useMe } from "../../auth";
import { money, percent } from "../../money";
import { Button, ErrorMsg } from "../../ui";

export default function LateFees() {
  const { data: me } = useMe();
  const canApply = can(me, "billing:finalize");
  const qc = useQueryClient();
  const preview = useQuery({ queryKey: ["late-fees"], queryFn: () => api<LateFeePreview>("/late-fees/preview") });
  const [picked, setPicked] = useState<Set<number>>(new Set());
  const apply = useMutation({
    mutationFn: () => api("/late-fees/apply", { method: "POST", json: { invoice_ids: [...picked] } }),
    onSuccess: () => { setPicked(new Set()); qc.invalidateQueries({ queryKey: ["late-fees"] }); qc.invalidateQueries({ queryKey: ["charges"] }); },
  });
  const p = preview.data;
  const toggle = (id: number) => { const n = new Set(picked); if (n.has(id)) n.delete(id); else n.add(id); setPicked(n); };
  return (
    <div className="space-y-4">
      <p className="text-sm text-slate-600">
        Invoices past due beyond the grace period for clients with late fees turned on. Nothing is charged until you tick invoices and apply; the fee is then added to the client&apos;s next invoice. Rule is set in Settings.
      </p>
      {p && !p.configured && <p className="rounded border border-amber-300 bg-amber-50 p-2 text-sm">No late-fee rule is set. Add a percent or a flat fee in Settings → Late fees.</p>}
      {p && p.configured && <p className="text-sm">Rule: {percent(p.percent_bp)} of balance{p.flat_cents > 0 && <> + {money(p.flat_cents)} flat</>}, after {p.grace_days} grace days, at most {p.max_per_invoice} per invoice.</p>}
      <ErrorMsg error={preview.error ?? apply.error} />
      <table className="w-full rounded-lg border border-slate-200 bg-surface text-left text-sm">
        <thead className="border-b border-slate-200 text-slate-500"><tr><th className="p-2" /><th>Invoice</th><th>Client</th><th>Due</th><th className="text-right">Days late</th><th className="text-right">Balance</th><th className="text-right">Fee</th></tr></thead>
        <tbody>
          {p?.rows.map((r) => (
            <tr key={r.invoice_id} className="border-t border-slate-100">
              <td className="p-2"><input type="checkbox" aria-label={`Charge ${r.invoice_number}`} disabled={!canApply} checked={picked.has(r.invoice_id)} onChange={() => toggle(r.invoice_id)} /></td>
              <td><Link className="text-blue-700 underline" to={`/billing/invoices/${r.invoice_id}`}>{r.invoice_number}</Link></td>
              <td>{r.organization_name}</td>
              <td>{r.due_date}</td>
              <td className="text-right">{r.days_overdue}</td>
              <td className="text-right">{money(r.balance_cents)}</td>
              <td className="text-right font-medium">{money(r.fee_cents)}{r.fees_so_far > 0 && <span className="ml-1 text-xs text-slate-500">({r.fees_so_far} already)</span>}</td>
            </tr>
          ))}
          {p && p.rows.length === 0 && <tr><td colSpan={7} className="p-3 text-slate-500">No invoices qualify right now.</td></tr>}
        </tbody>
      </table>
      {canApply && picked.size > 0 && <Button onClick={() => apply.mutate()}>Charge {picked.size} late fee{picked.size > 1 ? "s" : ""}</Button>}
    </div>
  );
}
