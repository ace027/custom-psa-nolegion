import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { procurement } from "../api";
import { ErrorMsg, Card } from "../ui";

const STATUS_LABEL = { in_stock: "Reserved", delivered: "Delivered", consumed: "Used" } as const;

export default function OrgInventoryCard({ orgId }: { orgId: number }) {
  const q = useQuery({ queryKey: ["procurement", "org-inventory", orgId], queryFn: () => procurement.orgInventory(orgId) });
  const rows = q.data ?? [];
  return (
    <Card title="Hardware and inventory">
      <ErrorMsg error={q.error} />
      {q.isLoading && <p className="text-sm text-slate-500">Loading…</p>}
      {q.data && rows.length === 0 && <p className="text-sm text-slate-500">No hardware delivered or reserved for this client.</p>}
      {rows.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <caption className="sr-only">Client inventory</caption>
            <thead>
              <tr className="border-b border-slate-200 text-left text-slate-500">
                <th scope="col" className="py-1.5">Item</th><th scope="col">Serial</th><th scope="col">Status</th>
                <th scope="col">Delivered</th><th scope="col">Asset</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((i) => (
                <tr key={i.id} className="border-b border-slate-100">
                  <td className="py-1.5">{i.description}{i.quantity > 1 ? ` × ${i.quantity}` : ""}</td>
                  <td className="break-all">{i.serial_number ?? "—"}</td>
                  <td>{STATUS_LABEL[i.status]}</td>
                  <td>{i.delivered_on ?? "—"}</td>
                  <td>{i.asset_id ? <Link className="text-blue-700 hover:underline" to={`/organizations/${orgId}`}>Asset #{i.asset_id}</Link> : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
