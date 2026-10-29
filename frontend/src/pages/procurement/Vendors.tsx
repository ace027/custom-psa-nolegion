import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useState } from "react";
import { Vendor, procurement } from "../../api";
import { can, useMe } from "../../auth";
import { Button, Card, ErrorMsg, Field, inputCls } from "../../ui";

const blank = { name: "", account_number: "", email: "", phone: "", website: "", notes: "" };

export default function Vendors() {
  const { data: me } = useMe();
  const write = can(me, "procurement:write");
  const qc = useQueryClient();
  const [archived, setArchived] = useState(false);
  const [editing, setEditing] = useState<Vendor | "new" | null>(null);
  const q = useQuery({ queryKey: ["procurement", "vendors", archived], queryFn: () => procurement.vendors(archived) });
  const toggle = useMutation({
    mutationFn: (v: Vendor) => procurement.updateVendor(v.id, { archived: !v.archived_at }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["procurement", "vendors"] }),
  });
  const rows = q.data ?? [];
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex items-center gap-1 text-sm">
          <input type="checkbox" checked={archived} onChange={(e) => setArchived(e.target.checked)} />Show archived
        </label>
        {write && <Button onClick={() => setEditing(editing === "new" ? null : "new")}>{editing === "new" ? "Close" : "Add vendor"}</Button>}
      </div>
      {write && editing && (
        <VendorForm
          key={editing === "new" ? "new" : editing.id}
          vendor={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
          onDone={() => { setEditing(null); qc.invalidateQueries({ queryKey: ["procurement", "vendors"] }); }}
        />
      )}
      <ErrorMsg error={q.error ?? toggle.error} />
      {q.isLoading && <p className="text-sm text-slate-500">Loading…</p>}
      {q.data && rows.length === 0 && <p className="text-sm text-slate-500">No vendors yet.</p>}
      {rows.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <caption className="sr-only">Vendors</caption>
            <thead>
              <tr className="border-b border-slate-200 text-left text-slate-500">
                <th scope="col" className="py-1.5">Name</th><th scope="col">Account</th><th scope="col">Contact</th>
                <th scope="col">Website</th><th scope="col"><span className="sr-only">Actions</span></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((v) => (
                <tr key={v.id} className="border-b border-slate-100 align-top">
                  <td className={`py-1.5 font-medium ${v.archived_at ? "text-slate-600 line-through" : ""}`}>{v.name}{v.archived_at && <span className="ml-2 rounded-full bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-700 no-underline inline-block">Archived</span>}</td>
                  <td>{v.account_number ?? "—"}</td>
                  <td className="break-words">{[v.email, v.phone].filter(Boolean).join(" · ") || "—"}</td>
                  <td className="break-words">{v.website ?? "—"}</td>
                  <td className="text-right">
                    {write && (
                      <span className="flex justify-end gap-2">
                        <Button variant="secondary" aria-label={`Edit ${v.name}`} onClick={() => setEditing(v)}>Edit</Button>
                        <Button variant="secondary" aria-label={`${v.archived_at ? "Restore" : "Archive"} ${v.name}`} disabled={toggle.isPending} onClick={() => toggle.mutate(v)}>
                          {v.archived_at ? "Restore" : "Archive"}
                        </Button>
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

function VendorForm({ vendor, onClose, onDone }: { vendor: Vendor | null; onClose: () => void; onDone: () => void }) {
  const [f, setF] = useState(
    vendor
      ? { name: vendor.name, account_number: vendor.account_number ?? "", email: vendor.email ?? "", phone: vendor.phone ?? "", website: vendor.website ?? "", notes: vendor.notes ?? "" }
      : blank,
  );
  const save = useMutation({
    mutationFn: () => {
      const json = {
        name: f.name.trim(),
        account_number: f.account_number.trim() || null,
        email: f.email.trim() || null,
        phone: f.phone.trim() || null,
        website: f.website.trim() || null,
        notes: f.notes.trim() || null,
      };
      return vendor ? procurement.updateVendor(vendor.id, json) : procurement.createVendor(json);
    },
    onSuccess: onDone,
  });
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
  const submit = (e: FormEvent) => { e.preventDefault(); save.mutate(); };
  return (
    <Card title={vendor ? `Edit ${vendor.name}` : "New vendor"} actions={<Button variant="secondary" onClick={onClose}>Cancel</Button>}>
      <form onSubmit={submit} className="grid gap-3 sm:grid-cols-3">
        <Field label="Vendor name"><input required className={inputCls} value={f.name} onChange={set("name")} /></Field>
        <Field label="Account number"><input className={inputCls} value={f.account_number} onChange={set("account_number")} /></Field>
        <Field label="Vendor email"><input type="email" className={inputCls} value={f.email} onChange={set("email")} /></Field>
        <Field label="Vendor phone"><input className={inputCls} value={f.phone} onChange={set("phone")} /></Field>
        <Field label="Website"><input className={inputCls} value={f.website} onChange={set("website")} /></Field>
        <div className="sm:col-span-3"><Field label="Notes"><textarea className={inputCls} rows={2} value={f.notes} onChange={set("notes")} /></Field></div>
        <div className="space-y-2 sm:col-span-3">
          <ErrorMsg error={save.error} />
          <Button type="submit" disabled={save.isPending || !f.name.trim()}>Save vendor</Button>
        </div>
      </form>
    </Card>
  );
}
