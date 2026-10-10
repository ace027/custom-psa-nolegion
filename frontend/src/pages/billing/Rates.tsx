import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { WorkTypeBilling, api } from "../../api";
import { can, useMe } from "../../auth";
import { money, parseMoney } from "../../money";
import { Card, ErrorMsg, inputCls } from "../../ui";

export default function Rates() {
  const { data: me } = useMe();
  const canWrite = can(me, "billing:write");
  const qc = useQueryClient();
  const list = useQuery({ queryKey: ["wt-billing"], queryFn: () => api<WorkTypeBilling[]>("/billing/work-types") });
  const save = useMutation({
    mutationFn: ({ id, json }: { id: number; json: object }) => api(`/billing/work-types/${id}`, { method: "PATCH", json }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["wt-billing"] }),
  });
  return (
    <div className="space-y-4">
      <Card title="Hourly rates by work type">
        <p className="mb-2 text-sm text-slate-600">
          Time is billed at these rates. <b>A work type with no rate is never billed at $0</b>: its time stays unbilled and the run warns you. Client-specific rates are set on the client's page.
        </p>
        <ErrorMsg error={list.error ?? save.error} />
        <table className="w-full text-left text-sm">
          <thead className="text-slate-500"><tr><th>Work type</th><th>Hourly rate ($)</th><th>Taxable</th><th>Not covered by blocks</th></tr></thead>
          <tbody>
            {list.data?.filter((w) => !w.archived_at).map((w) => <RateRow key={w.id} w={w} canWrite={canWrite} onSave={(json) => save.mutate({ id: w.id, json })} />)}
          </tbody>
        </table>
        <p className="mt-2 text-xs text-slate-500">Whether labor is taxable depends on your state. The tax rate itself is set per client. Billable minutes round up to your billing increment (Settings).</p>
      </Card>
    </div>
  );
}

function RateRow({ w, canWrite, onSave }: { w: WorkTypeBilling; canWrite: boolean; onSave: (json: object) => void }) {
  const [text, setText] = useState(w.rate_cents === null ? "" : money(w.rate_cents).replace("$", ""));
  const [invalid, setInvalid] = useState(false);
  const errId = `rate-err-${w.id}`;
  return (
    <tr className="border-t border-slate-100">
      <td className="py-1">{w.name}</td>
      <td><input aria-label={`${w.name} hourly rate`} aria-invalid={invalid} aria-describedby={invalid ? errId : undefined} className={inputCls + " w-28"} disabled={!canWrite} placeholder="not set" value={text} onChange={(e) => { setText(e.target.value); setInvalid(false); }}
        onBlur={() => { const c = text.trim() === "" ? null : parseMoney(text); if (text.trim() !== "" && c === null) { setInvalid(true); return; } setInvalid(false); if (c !== w.rate_cents) onSave({ rate_cents: c }); }} />
        {invalid && <div id={errId} role="alert" className="text-xs text-red-600">Enter a valid rate, e.g. 150.00</div>}</td>
      <td><input aria-label={`${w.name} taxable`} type="checkbox" disabled={!canWrite} checked={w.taxable} onChange={(e) => onSave({ taxable: e.target.checked })} /></td>
      <td><input aria-label={`${w.name} not covered by blocks`} type="checkbox" disabled={!canWrite} checked={!w.block_covered} onChange={(e) => onSave({ block_covered: !e.target.checked })} /></td>
    </tr>
  );
}
