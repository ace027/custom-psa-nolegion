import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Asset, Organization, WARRANTY_LABEL, api } from "../api";
import { can, useMe } from "../auth";
import { Button, Card, ErrorMsg, Field, WarrantyBadge, inputCls } from "../ui";

export default function OrgAssetsCard({ org }: { org: Organization }) {
  const { data: me } = useMe();
  const qc = useQueryClient();
  const [retired, setRetired] = useState(false);
  const [editing, setEditing] = useState<Asset | null>(null);
  const [date, setDate] = useState("");
  const [reason, setReason] = useState("");
  const q = useQuery({
    queryKey: ["assets", org.id, retired],
    queryFn: () => api<Asset[]>(`/organizations/${org.id}/assets?include_retired=${retired}`),
  });
  const done = () => { setEditing(null); setDate(""); setReason(""); qc.invalidateQueries({ queryKey: ["assets", org.id] }); qc.invalidateQueries({ queryKey: ["org", org.id] }); };
  const override = useMutation({
    mutationFn: () => api(`/assets/${editing!.id}/overrides/warranty_end`, { method: "PUT", json: { value: date, reason } }),
    onSuccess: done,
  });
  const clear = useMutation({ mutationFn: (a: Asset) => api(`/assets/${a.id}/overrides/warranty_end`, { method: "DELETE" }), onSuccess: done });
  const share = useMutation({
    mutationFn: () => api(`/organizations/${org.id}/assets-sharing`, { method: "PUT", json: { published: !org.assets_published } }),
    onSuccess: done,
  });
  const canEdit = can(me, "org:write");
  return (
    <Card
      title="Devices and warranty"
      actions={<label className="flex items-center gap-1 text-xs"><input type="checkbox" checked={retired} onChange={(e) => setRetired(e.target.checked)} />Show retired</label>}
    >
      <ErrorMsg error={q.error ?? override.error ?? clear.error ?? share.error} />
      {q.data?.length === 0 && <p className="text-sm text-slate-500">No devices yet. Map this client in Integrations and run a sync.</p>}
      {!!q.data?.length && (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-slate-200 text-slate-500"><tr><th className="p-1">Device</th><th>Type</th><th>Make / model</th><th>Serial</th><th>Warranty ends</th><th /></tr></thead>
            <tbody>
              {q.data.map((a) => (
                <tr key={a.id} className={`border-b border-slate-100 ${a.retired_at ? "text-slate-400" : ""}`}>
                  <td className="p-1">{a.name}{a.retired_at && " (retired)"}</td>
                  <td>{a.kind}</td>
                  <td>{[a.manufacturer, a.model].filter(Boolean).join(" ") || "—"}</td>
                  <td>{a.serial ?? "—"}</td>
                  <td>
                    {a.warranty_end ?? "—"} <WarrantyBadge state={a.warranty_status} label={WARRANTY_LABEL[a.warranty_status]} />
                    {a.warranty_overridden && <span className="ml-1 text-xs text-purple-700" title="A tech corrected this date">corrected</span>}
                    {a.conflict && <span className="ml-1 text-xs text-amber-700" title="NinjaOne and Hudu disagree on the date">sources disagree</span>}
                  </td>
                  <td className="whitespace-nowrap p-1 text-right">
                    {canEdit && !a.retired_at && <Button variant="secondary" onClick={() => setEditing(a)}>Correct date</Button>}
                    {canEdit && a.warranty_overridden && <Button variant="secondary" className="ml-1" onClick={() => clear.mutate(a)}>Undo</Button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {editing && (
        <form className="mt-3 grid gap-2 rounded border border-slate-200 p-3 sm:grid-cols-3" onSubmit={(e) => { e.preventDefault(); override.mutate(); }}>
          <p className="col-span-full text-sm font-medium">Correct the warranty end date for {editing.name}. It is kept even when the vendor syncs a different date.</p>
          <Field label="Warranty ends"><input className={inputCls} type="date" required value={date} onChange={(e) => setDate(e.target.value)} /></Field>
          <Field label="Reason"><input className={inputCls} required value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
          <div className="flex items-end gap-2"><Button type="submit" disabled={override.isPending}>Save</Button><Button type="button" variant="secondary" onClick={() => setEditing(null)}>Cancel</Button></div>
        </form>
      )}
      {can(me, "portal:manage") && (
        <div className="mt-4 flex items-center justify-between border-t border-slate-200 pt-3 text-sm">
          <span>
            Client portal page: <b>{org.assets_published ? "published" : "not published"}</b>
            <span className="ml-2 text-slate-500">Only contacts you flag for devices can see it.</span>
          </span>
          <Button variant="secondary" onClick={() => share.mutate()}>{org.assets_published ? "Withdraw" : "Publish to portal"}</Button>
        </div>
      )}
    </Card>
  );
}
