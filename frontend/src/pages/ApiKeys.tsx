import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { ApiKey, createApiKey, listApiKeys, revokeApiKey } from "../api";
import { useMe } from "../auth";
import { Button, Card, ErrorMsg, Field, fmt, inputCls } from "../ui";

const FORBIDDEN = ["user:manage", "apikey:manage", "portal:manage"];
const STATE_STYLE = { active: "text-green-700", expired: "text-amber-700", revoked: "text-slate-500" };

export default function ApiKeys() {
  const qc = useQueryClient();
  const me = useMe();
  const list = useQuery({ queryKey: ["api-keys"], queryFn: listApiKeys });
  const [name, setName] = useState("");
  const [days, setDays] = useState(365);
  const [perms, setPerms] = useState<string[]>([]);
  const [token, setToken] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const offered = (me.data?.permissions ?? []).filter((p) => !FORBIDDEN.includes(p)).sort();
  const create = useMutation({
    mutationFn: () => createApiKey({ name, permissions: perms, expires_in_days: days }),
    onSuccess: (r) => {
      setToken(r.token);
      setCopied(false);
      setName("");
      setPerms([]);
      qc.invalidateQueries({ queryKey: ["api-keys"] });
    },
  });
  const revoke = useMutation({
    mutationFn: (id: number) => revokeApiKey(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["api-keys"] }),
  });
  const onRevoke = (k: ApiKey) => {
    if (window.confirm(`Revoke the key "${k.name}"? Anything using it stops working immediately.`)) revoke.mutate(k.id);
  };
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold tracking-tight">API keys</h1>
      <p className="text-sm text-slate-600">
        Keys let scripts and tools call the API with <code>Authorization: Bearer psa_…</code>. A key can only use the permissions you give it,
        and only while its owner still holds them.
      </p>
      {token && (
        <Card title="Your new key">
          <p role="alert" className="mb-2 rounded bg-amber-50 px-3 py-2 text-sm text-amber-800">Copy this key now. It will not be shown again.</p>
          <div className="flex gap-2">
            <input aria-label="New API key" readOnly className={`${inputCls} font-mono`} value={token} onFocus={(e) => e.currentTarget.select()} />
            <Button variant="secondary" onClick={() => { navigator.clipboard?.writeText(token); setCopied(true); }}>{copied ? "Copied" : "Copy"}</Button>
            <Button variant="secondary" onClick={() => setToken(null)}>Dismiss</Button>
          </div>
        </Card>
      )}
      <Card title="Keys">
        <ErrorMsg error={list.error ?? revoke.error} />
        <table className="w-full text-left text-sm">
          <thead className="border-b border-slate-200 text-slate-500">
            <tr><th className="p-1">Name</th><th>Key</th><th>Permissions</th><th>Owner</th><th>State</th><th>Expires</th><th>Last used</th><th /></tr>
          </thead>
          <tbody>
            {list.data?.map((k) => (
              <tr key={k.id} className="border-b border-slate-100">
                <td className="p-1">{k.name}</td>
                <td className="font-mono">{`psa_${k.prefix}_…`}</td>
                <td>{k.permissions.join(", ")}</td>
                <td>{k.owner_name}</td>
                <td className={STATE_STYLE[k.state]}>{k.state}</td>
                <td>{fmt(k.expires_at)}</td>
                <td>{fmt(k.last_used_at)}</td>
                <td>{k.state === "active" && <Button variant="danger" onClick={() => onRevoke(k)} aria-label={`Revoke ${k.name}`}>Revoke</Button>}</td>
              </tr>
            ))}
            {list.data?.length === 0 && <tr><td colSpan={8} className="p-2 text-slate-500">No API keys yet.</td></tr>}
          </tbody>
        </table>
      </Card>
      <Card title="Create a key">
        <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); create.mutate(); }}>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Name"><input className={inputCls} required maxLength={100} value={name} onChange={(e) => setName(e.target.value)} /></Field>
            <Field label="Expires in (days)">
              <input className={inputCls} type="number" min={1} max={730} required value={days} onChange={(e) => setDays(Number(e.target.value))} />
            </Field>
          </div>
          <fieldset>
            <legend className="mb-1 text-sm font-medium">Permissions</legend>
            <div className="grid gap-1 sm:grid-cols-3">
              {offered.map((p) => (
                <label key={p} className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={perms.includes(p)} onChange={(e) => setPerms(e.target.checked ? [...perms, p] : perms.filter((x) => x !== p))} />
                  {p}
                </label>
              ))}
            </div>
          </fieldset>
          <ErrorMsg error={create.error} />
          <Button type="submit" disabled={create.isPending || perms.length === 0}>Create key</Button>
        </form>
      </Card>
    </div>
  );
}
