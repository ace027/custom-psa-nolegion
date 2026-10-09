import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { Organization, Page, api } from "../api";
import { can, useMe } from "../auth";
import { Button, ErrorMsg, Field, inputCls } from "../ui";

export default function Organizations() {
  const { data: me } = useMe();
  const qc = useQueryClient();
  const [q, setQ] = useState("");
  const [showArchived, setShowArchived] = useState(false);
  const [name, setName] = useState("");
  const list = useQuery({
    queryKey: ["orgs", q, showArchived],
    queryFn: () =>
      api<Page<Organization>>(
        `/organizations?limit=200&include_archived=${showArchived}&q=${encodeURIComponent(q)}`,
      ),
  });
  const create = useMutation({
    mutationFn: () => api<Organization>("/organizations", { method: "POST", json: { name } }),
    onSuccess: () => {
      setName("");
      qc.invalidateQueries({ queryKey: ["orgs"] });
    },
  });
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold tracking-tight">Organizations</h1>
      <div className="flex flex-wrap items-end gap-4">
        <div className="w-64">
          <Field label="Search">
            <input className={inputCls} value={q} onChange={(e) => setQ(e.target.value)} />
          </Field>
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={showArchived} onChange={(e) => setShowArchived(e.target.checked)} />
          Show archived
        </label>
      </div>
      {can(me, "org:write") && (
        <form
          className="flex items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            create.mutate();
          }}
        >
          <div className="w-64">
            <Field label="New organization">
              <input className={inputCls} value={name} onChange={(e) => setName(e.target.value)} required />
            </Field>
          </div>
          <Button type="submit" disabled={create.isPending}>
            Add
          </Button>
        </form>
      )}
      <ErrorMsg error={create.error ?? list.error} />
      <ul className="divide-y divide-slate-200 rounded-lg border border-slate-200 bg-surface">
        {list.data?.items.map((o) => (
          <li key={o.id} className="px-4 py-2">
            <Link to={`/organizations/${o.id}`} className="font-medium text-blue-700 hover:underline">
              {o.name}
            </Link>
            {o.status === "inactive" && <span className="ml-2 text-xs text-slate-500">inactive</span>}
            {o.status === "prospect" && <span className="ml-2 rounded bg-violet-100 px-1.5 text-xs text-violet-800">prospect</span>}
            {o.archived_at && <span className="ml-2 text-xs text-slate-500">archived</span>}
          </li>
        ))}
        {list.data?.items.length === 0 && <li className="px-4 py-3 text-sm text-slate-500">No organizations.</li>}
      </ul>
    </div>
  );
}
