import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useState } from "react";
import { Link } from "react-router-dom";
import { Asset, InventoryItem, InventoryStatus, Organization, api, bpPercent, procurement } from "../../api";
import { can, useMe } from "../../auth";
import { money } from "../../money";
import { Button, Card, ErrorMsg, Field, inputCls } from "../../ui";
import { ProcurementNav } from "./PurchaseOrders";

export const ITEM_STATUS_LABEL: Record<InventoryStatus, string> = { in_stock: "In stock", delivered: "Delivered", consumed: "Used internally" };

export default function Inventory() {
  const { data: me } = useMe();
  const write = can(me, "procurement:write");
  const qc = useQueryClient();
  const [status, setStatus] = useState<InventoryStatus | "">("");
  const [org, setOrg] = useState("");
  const [search, setSearch] = useState("");
  const [delivering, setDelivering] = useState<InventoryItem | null>(null);
  const [confirm, setConfirm] = useState<{ item: InventoryItem; kind: "undo" | "consume" } | null>(null);
  const orgs = useQuery({ queryKey: ["orgs-all"], queryFn: () => api<Organization[] | { items: Organization[] }>("/organizations") });
  const orgList = Array.isArray(orgs.data) ? orgs.data : orgs.data?.items ?? [];
  const q = useQuery({
    queryKey: ["procurement", "inventory", status, org, search],
    queryFn: () => procurement.inventory({ status, organization_id: org ? Number(org) : "", q: search.trim() }),
  });
  const act = useMutation({
    mutationFn: ({ item, kind }: { item: InventoryItem; kind: "undo" | "consume" }) =>
      kind === "undo" ? procurement.undoDelivery(item.id) : procurement.consume(item.id),
    onSuccess: () => { setConfirm(null); qc.invalidateQueries({ queryKey: ["procurement"] }); },
  });
  const rows = q.data ?? [];
  return (
    <div className="space-y-4">
      <ProcurementNav />
      <div className="flex flex-wrap items-end gap-3">
        <Field label="Status">
          <select className={inputCls} value={status} onChange={(e) => setStatus(e.target.value as InventoryStatus | "")}>
            <option value="">All</option>
            {(Object.keys(ITEM_STATUS_LABEL) as InventoryStatus[]).map((s) => <option key={s} value={s}>{ITEM_STATUS_LABEL[s]}</option>)}
          </select>
        </Field>
        <Field label="Client">
          <select className={inputCls} value={org} onChange={(e) => setOrg(e.target.value)}>
            <option value="">All clients</option>
            {orgList.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
          </select>
        </Field>
        <Field label="Search"><input type="search" className={inputCls} value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Description or serial" /></Field>
      </div>
      {write && delivering && (
        <DeliverDialog key={delivering.id} item={delivering} orgs={orgList} onClose={() => setDelivering(null)}
          onDone={() => { setDelivering(null); qc.invalidateQueries({ queryKey: ["procurement"] }); }} />
      )}
      {write && confirm && (
        <div role="alertdialog" aria-label={confirm.kind === "undo" ? "Confirm undo delivery" : "Confirm consume"} className="flex flex-wrap items-center gap-3 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm">
          <span>
            {confirm.kind === "undo"
              ? `Take back ${confirm.item.description} from ${confirm.item.organization_name ?? "the client"}? Its charge is voided.`
              : `Mark ${confirm.item.description} as used internally? It will never be billed.`}
          </span>
          <Button variant="danger" disabled={act.isPending} onClick={() => act.mutate(confirm)}>{confirm.kind === "undo" ? "Confirm undo" : "Confirm consume"}</Button>
          <Button variant="secondary" onClick={() => { setConfirm(null); act.reset(); }}>Keep as is</Button>
        </div>
      )}
      <ErrorMsg error={q.error ?? act.error} />
      {q.isLoading && <p className="text-sm text-slate-500">Loading…</p>}
      {q.data && rows.length === 0 && <p className="text-sm text-slate-500">No inventory matches. Receive a purchase order to add stock.</p>}
      {rows.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <caption className="sr-only">Inventory</caption>
            <thead>
              <tr className="border-b border-slate-200 text-left text-slate-500">
                <th scope="col" className="py-1.5">Item</th><th scope="col">Serial</th><th scope="col">Qty</th>
                <th scope="col" className="text-right">Cost</th><th scope="col">Markup</th><th scope="col">Client</th><th scope="col">Status</th>
                <th scope="col"><span className="sr-only">Actions</span></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((i) => (
                <tr key={i.id} className="border-b border-slate-100 align-top">
                  <td className="py-1.5">{i.description}</td>
                  <td className="break-all">{i.serial_number ?? "—"}</td>
                  <td>{i.quantity}</td>
                  <td className="text-right">{money(i.unit_cost_cents)}</td>
                  <td>{i.markup_bp === null ? "—" : bpPercent(i.markup_bp)}</td>
                  <td>{i.organization_id ? <Link className="text-blue-700 hover:underline" to={`/organizations/${i.organization_id}`}>{i.organization_name}</Link> : "—"}</td>
                  <td>{ITEM_STATUS_LABEL[i.status]}</td>
                  <td className="text-right">
                    {write && (
                      <span className="flex justify-end gap-2">
                        {i.status === "in_stock" && <Button variant="secondary" aria-label={`Deliver ${i.description}${i.serial_number ? ` ${i.serial_number}` : ""}`} onClick={() => setDelivering(i)}>Deliver</Button>}
                        {i.status === "in_stock" && <Button variant="secondary" aria-label={`Consume ${i.description}${i.serial_number ? ` ${i.serial_number}` : ""}`} onClick={() => { act.reset(); setConfirm({ item: i, kind: "consume" }); }}>Consume</Button>}
                        {i.status === "delivered" && <Button variant="secondary" aria-label={`Undo delivery of ${i.description}${i.serial_number ? ` ${i.serial_number}` : ""}`} onClick={() => { act.reset(); setConfirm({ item: i, kind: "undo" }); }}>Undo delivery</Button>}
                      </span>
                    )}
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

function DeliverDialog({ item, orgs, onClose, onDone }: { item: InventoryItem; orgs: Organization[]; onClose: () => void; onDone: () => void }) {
  const [orgId, setOrgId] = useState(item.organization_id ? String(item.organization_id) : "");
  const [qtyText, setQtyText] = useState(String(item.quantity));
  const [assetMode, setAssetMode] = useState<"none" | "link" | "create">("none");
  const [assetId, setAssetId] = useState("");
  const [bad, setBad] = useState("");
  const assets = useQuery({
    queryKey: ["org-assets", orgId],
    queryFn: () => api<Asset[]>(`/organizations/${orgId}/assets`),
    enabled: assetMode === "link" && orgId !== "",
  });
  const deliver = useMutation({
    mutationFn: (json: Parameters<typeof procurement.deliver>[1]) => procurement.deliver(item.id, json),
    onSuccess: onDone,
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const n = Number(qtyText);
    if (!orgId) return setBad("Choose a client.");
    if (!Number.isInteger(n) || n < 1 || n > item.quantity) return setBad(`Quantity must be a whole number from 1 to ${item.quantity}.`);
    if (assetMode === "link" && !assetId) return setBad("Choose the asset to link.");
    setBad("");
    deliver.mutate({
      organization_id: Number(orgId),
      quantity: item.serial_number ? 1 : n,
      asset_id: assetMode === "link" ? Number(assetId) : null,
      create_asset: assetMode === "create",
    });
  };
  return (
    <Card title={`Deliver ${item.description}`} actions={<Button variant="secondary" onClick={onClose}>Cancel</Button>}>
      <form onSubmit={submit} className="space-y-3" aria-label="Deliver to client">
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Deliver to client">
            <select className={inputCls} value={orgId} onChange={(e) => { setOrgId(e.target.value); setAssetId(""); }}>
              <option value="">Choose a client</option>
              {orgs.filter((o) => !o.archived_at).map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
            </select>
          </Field>
          {!item.serial_number && item.quantity > 1 && (
            <Field label="Quantity to deliver"><input className={inputCls} type="number" min={1} max={item.quantity} value={qtyText} onChange={(e) => setQtyText(e.target.value)} /></Field>
          )}
          <Field label="Asset">
            <select className={inputCls} value={assetMode} onChange={(e) => setAssetMode(e.target.value as "none" | "link" | "create")}>
              <option value="none">No asset</option>
              <option value="create">Create a new asset</option>
              <option value="link">Link an existing asset</option>
            </select>
          </Field>
          {assetMode === "link" && (
            <Field label="Existing asset">
              <select className={inputCls} value={assetId} onChange={(e) => setAssetId(e.target.value)} disabled={!orgId}>
                <option value="">{orgId ? "Choose an asset" : "Choose a client first"}</option>
                {(assets.data ?? []).map((a) => <option key={a.id} value={a.id}>{a.name}{a.serial ? ` (${a.serial})` : ""}</option>)}
              </select>
            </Field>
          )}
        </div>
        {bad && <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{bad}</p>}
        <ErrorMsg error={deliver.error ?? assets.error} />
        <Button type="submit" disabled={deliver.isPending}>Deliver</Button>
      </form>
    </Card>
  );
}
