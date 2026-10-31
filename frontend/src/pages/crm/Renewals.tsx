import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { RenewalReminder, crmApi } from "../../api";
import { can, useMe } from "../../auth";
import { Button, ErrorMsg } from "../../ui";
import { clientRoute } from "../../clientScope";

/** Whole days from today (local) to an ISO date; negative when past. */
export function daysLeft(iso: string, now = new Date()): number {
  const [y, m, d] = iso.split("-").map(Number);
  const end = Date.UTC(y, m - 1, d);
  const today = Date.UTC(now.getFullYear(), now.getMonth(), now.getDate());
  return Math.round((end - today) / 86_400_000);
}

export const useOpenRenewals = (enabled = true) =>
  useQuery({
    queryKey: ["crm", "renewals", "open"],
    enabled,
    queryFn: async () => (await crmApi.renewals("open")).sort((a, b) => a.due_on.localeCompare(b.due_on)),
  });

export default function Renewals() {
  const { data: me } = useMe();
  const write = can(me, "crm:write");
  const qc = useQueryClient();
  const q = useOpenRenewals();
  const dismiss = useMutation({
    mutationFn: (r: RenewalReminder) => crmApi.dismissRenewal(r.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["crm"] }),
  });
  const rows = q.data ?? [];
  return (
    <div className="space-y-3">
      <ErrorMsg error={q.error ?? dismiss.error} />
      {q.data && rows.length === 0 && <p className="text-sm text-slate-500">No renewals are due. Reminders appear before an agreement ends.</p>}
      {rows.length > 0 && (
        <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <caption className="sr-only">Open renewal reminders</caption>
          <thead>
            <tr className="border-b border-slate-200 text-left text-slate-500">
              <th scope="col" className="py-1.5">Client</th>
              <th scope="col">Agreement</th>
              <th scope="col">Ends</th>
              <th scope="col" className="text-right">Days left</th>
              <th scope="col">Opportunity</th>
              <th scope="col"><span className="sr-only">Actions</span></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="border-b border-slate-100">
                <td className="py-1.5"><Link className="text-blue-700 hover:underline" to={clientRoute(r.organization_id)}>{r.organization_name}</Link></td>
                <td>{r.agreement_name}</td>
                <td>{r.due_on}</td>
                <td className="text-right tabular-nums">{daysLeft(r.due_on)}</td>
                <td>{r.opportunity_id ? <Link className="text-blue-700 hover:underline" to={`/crm/opportunities/${r.opportunity_id}`}>Renewal opportunity</Link> : <span className="text-slate-400">None</span>}</td>
                <td className="text-right">
                  {write && <Button variant="secondary" disabled={dismiss.isPending} onClick={() => dismiss.mutate(r)} aria-label={`Dismiss ${r.agreement_name}`}>Dismiss</Button>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
      )}
    </div>
  );
}
