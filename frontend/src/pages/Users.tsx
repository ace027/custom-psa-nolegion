import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { ROLES, Role, User, api } from "../api";
import { can, useMe } from "../auth";
import { Button, ErrorMsg, Field, inputCls } from "../ui";

export default function Users() {
  const { data: me } = useMe();
  const admin = can(me, "user:manage");
  const qc = useQueryClient();
  const users = useQuery({ queryKey: ["users"], queryFn: () => api<User[]>("/users") });
  const refresh = () => qc.invalidateQueries({ queryKey: ["users"] });
  const patch = useMutation({
    mutationFn: ({ id, ...json }: { id: number; role?: Role; is_active?: boolean }) =>
      api(`/users/${id}`, { method: "PATCH", json }),
    onSuccess: refresh,
  });
  const [form, setForm] = useState({ email: "", display_name: "", role: "tech" as Role });
  const create = useMutation({
    mutationFn: () => api("/users", { method: "POST", json: form }),
    onSuccess: () => {
      setForm({ email: "", display_name: "", role: "tech" });
      refresh();
    },
  });
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold tracking-tight">Users</h1>
      <p className="text-sm text-slate-600">
        Staff sign in with Microsoft Entra ID, but only after an admin has added them here.
      </p>
      <ErrorMsg error={patch.error ?? create.error ?? users.error} />
      <table className="w-full rounded-lg border border-slate-200 bg-surface text-left text-sm">
        <thead className="border-b border-slate-200 text-slate-500">
          <tr><th className="p-2">Name</th><th>Email</th><th>Role</th><th>Active</th></tr>
        </thead>
        <tbody>
          {users.data?.map((u) => (
            <tr key={u.id} className="border-b border-slate-100">
              <td className="p-2">{u.display_name}</td>
              <td>{u.email}</td>
              <td>
                {admin && u.id !== me?.id ? (
                  <select className={inputCls} value={u.role} onChange={(e) => patch.mutate({ id: u.id, role: e.target.value as Role })}>
                    {ROLES.map((r) => <option key={r}>{r}</option>)}
                  </select>
                ) : u.role}
              </td>
              <td>
                {admin && u.id !== me?.id ? (
                  <Button variant="secondary" onClick={() => patch.mutate({ id: u.id, is_active: !u.is_active })}>
                    {u.is_active ? "Deactivate" : "Activate"}
                  </Button>
                ) : u.is_active ? "yes" : "no"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {admin && (
        <form className="flex flex-wrap items-end gap-2" onSubmit={(e) => { e.preventDefault(); create.mutate(); }}>
          <Field label="Email"><input className={inputCls} type="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></Field>
          <Field label="Display name"><input className={inputCls} required value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} /></Field>
          <Field label="Role">
            <select className={inputCls} value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as Role })}>
              {ROLES.map((r) => <option key={r}>{r}</option>)}
            </select>
          </Field>
          <Button type="submit">Pre-provision user</Button>
        </form>
      )}
    </div>
  );
}
