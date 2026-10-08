import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { ClientMap, Integration, Organization, SyncRun, api } from "../api";
import { Button, Card, ErrorMsg, Field, fmt, inputCls } from "../ui";

const STATUS_STYLE = { ok: "text-green-700", error: "text-red-700", unknown: "text-slate-500" };
const CRED_FIELDS = {
  ninjaone: [["client_id", "Client ID"], ["client_secret", "Client secret"]],
  hudu: [["api_key", "API key"]],
} as const;
const HUDU_CONFIG = JSON.stringify(
  { layouts: { Switches: "network", Firewalls: "network" }, warranty_end_field: "Warranty Expiration" },
  null,
  2,
);

export default function Integrations() {
  const list = useQuery({ queryKey: ["integrations"], queryFn: () => api<Integration[]>("/integrations") });
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Integrations</h1>
      <p className="text-sm text-slate-600">
        The PSA only reads from these systems; it never changes anything in them. Use a dedicated read-only account for each.
        Credentials are stored encrypted and are never shown again after you save them.
      </p>
      <ErrorMsg error={list.error} />
      {list.data?.map((i) => <IntegrationCard key={i.id} integration={i} />)}
      {list.data?.length === 0 && <p className="text-sm text-slate-500">No vendors connected yet.</p>}
      <ConnectForm />
    </div>
  );
}

function IntegrationCard({ integration: i }: { integration: Integration }) {
  const qc = useQueryClient();
  const refresh = () => qc.invalidateQueries({ queryKey: ["integrations"] });
  const [open, setOpen] = useState(false);
  const [rotate, setRotate] = useState<Record<string, string> | null>(null);
  const test = useMutation({
    mutationFn: () => api<{ ok: boolean; error: string | null }>(`/integrations/${i.id}/test`, { method: "POST" }),
    onSuccess: refresh,
  });
  const sync = useMutation({ mutationFn: () => api(`/integrations/${i.id}/sync`, { method: "POST" }), onSuccess: refresh });
  const toggle = useMutation({
    mutationFn: () => api(`/integrations/${i.id}`, { method: "PATCH", json: { enabled: !i.enabled } }),
    onSuccess: refresh,
  });
  const save = useMutation({
    mutationFn: () => api(`/integrations/${i.id}`, { method: "PATCH", json: { credentials: rotate } }),
    onSuccess: () => { setRotate(null); refresh(); },
  });
  return (
    <Card
      title={`${i.name} (${i.kind === "ninjaone" ? "NinjaOne" : "Hudu"})`}
      actions={<span className={`text-sm font-medium ${STATUS_STYLE[i.status]}`}>{i.enabled ? i.status : "turned off"}</span>}
    >
      <dl className="grid gap-x-4 gap-y-1 text-sm sm:grid-cols-2">
        <div><dt className="inline text-slate-500">Address: </dt><dd className="inline">{i.base_url}</dd></div>
        <div><dt className="inline text-slate-500">Credentials: </dt><dd className="inline">{i.credentials_set ? `set ${fmt(i.credentials_set_at)}` : "not set"}</dd></div>
        <div><dt className="inline text-slate-500">Last successful sync: </dt><dd className="inline">{fmt(i.last_sync_at)}</dd></div>
        {i.sync_requested && <div className="text-blue-700">Sync requested; the worker will pick it up within a minute.</div>}
      </dl>
      {i.last_error && <p role="alert" className="mt-2 rounded bg-red-50 px-3 py-2 text-sm text-red-700">{i.last_error}</p>}
      {test.data && (
        <p role="status" className={`mt-2 text-sm ${test.data.ok ? "text-green-700" : "text-red-700"}`}>
          {test.data.ok ? "Connection works." : `Connection failed: ${test.data.error}`}
        </p>
      )}
      <ErrorMsg error={test.error ?? sync.error ?? toggle.error ?? save.error} />
      <div className="mt-3 flex flex-wrap gap-2">
        <Button variant="secondary" onClick={() => test.mutate()} disabled={test.isPending}>Test connection</Button>
        <Button variant="secondary" onClick={() => sync.mutate()} disabled={!i.enabled || sync.isPending}>Sync now</Button>
        <Button variant="secondary" onClick={() => setOpen(!open)}>{open ? "Hide" : "Clients and history"}</Button>
        <Button variant="secondary" onClick={() => setRotate(rotate ? null : {})}>Replace credentials</Button>
        <Button variant="danger" onClick={() => toggle.mutate()}>{i.enabled ? "Turn off" : "Turn on"}</Button>
      </div>
      {rotate && (
        <form className="mt-3 grid gap-2 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
          {CRED_FIELDS[i.kind].map(([key, label]) => (
            <Field key={key} label={label}>
              <input className={inputCls} type="password" autoComplete="off" required value={rotate[key] ?? ""} onChange={(e) => setRotate({ ...rotate, [key]: e.target.value })} />
            </Field>
          ))}
          <div className="col-span-full"><Button type="submit" disabled={save.isPending}>Save new credentials</Button></div>
        </form>
      )}
      {open && <Detail integration={i} />}
    </Card>
  );
}

function Detail({ integration: i }: { integration: Integration }) {
  const qc = useQueryClient();
  const clients = useQuery({ queryKey: ["integration-clients", i.id], queryFn: () => api<ClientMap[]>(`/integrations/${i.id}/clients`) });
  const runs = useQuery({ queryKey: ["integration-runs", i.id], queryFn: () => api<SyncRun[]>(`/integrations/${i.id}/runs`) });
  const orgs = useQuery({ queryKey: ["orgs-all"], queryFn: () => api<Organization[]>("/organizations") });
  const reload = () => qc.invalidateQueries({ queryKey: ["integration-clients", i.id] });
  const fetchClients = useMutation({ mutationFn: () => api(`/integrations/${i.id}/clients/refresh`, { method: "POST" }), onSuccess: reload });
  const map = useMutation({
    mutationFn: (v: { id: number; organization_id: number | null; ignored: boolean }) =>
      api(`/integrations/${i.id}/clients/${v.id}`, { method: "PUT", json: { organization_id: v.organization_id, ignored: v.ignored } }),
    onSuccess: reload,
  });
  const todo = clients.data?.filter((c) => c.needs_mapping).length ?? 0;
  return (
    <div className="mt-4 space-y-4 border-t border-slate-200 pt-3">
      <div>
        <div className="mb-1 flex items-center justify-between">
          <h3 className="text-sm font-medium">Vendor clients {todo > 0 && <span className="ml-1 rounded bg-amber-100 px-1.5 text-xs text-amber-800">{todo} to map</span>}</h3>
          <Button variant="secondary" onClick={() => fetchClients.mutate()} disabled={fetchClients.isPending}>Fetch client list</Button>
        </div>
        <ErrorMsg error={fetchClients.error ?? map.error} />
        <table className="w-full text-left text-sm">
          <tbody>
            {clients.data?.map((c) => (
              <tr key={c.id} className="border-b border-slate-100">
                <td className="p-1">{c.external_name}</td>
                <td className="p-1">
                  <select
                    aria-label={`Map ${c.external_name}`}
                    className={inputCls}
                    value={c.ignored ? "ignore" : (c.organization_id ?? "")}
                    onChange={(e) => {
                      const v = e.target.value;
                      map.mutate({ id: c.id, organization_id: v && v !== "ignore" ? Number(v) : null, ignored: v === "ignore" });
                    }}
                  >
                    <option value="">Not mapped yet</option>
                    <option value="ignore">Ignore this client</option>
                    {orgs.data?.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
                  </select>
                </td>
                <td className="p-1 text-xs text-slate-500">
                  {c.suggested_organization_id && (
                    <button className="text-blue-700 hover:underline" onClick={() => map.mutate({ id: c.id, organization_id: c.suggested_organization_id, ignored: false })}>
                      Use suggested match
                    </button>
                  )}
                </td>
              </tr>
            ))}
            {clients.data?.length === 0 && <tr><td className="p-2 text-slate-500">Nothing yet. Fetch the client list.</td></tr>}
          </tbody>
        </table>
      </div>
      <div>
        <h3 className="mb-1 text-sm font-medium">Recent syncs</h3>
        <table className="w-full text-left text-sm">
          <thead className="border-b border-slate-200 text-slate-500"><tr><th className="p-1">Started</th><th>Result</th><th>Added</th><th>Changed</th><th>Retired</th><th>Clients</th></tr></thead>
          <tbody>
            {runs.data?.map((r) => (
              <tr key={r.id} className="border-b border-slate-100" title={r.error ?? ""}>
                <td className="p-1">{fmt(r.started_at)}</td>
                <td className={r.status === "ok" ? "text-green-700" : r.status === "partial" ? "text-amber-700" : "text-red-700"}>{r.status}</td>
                <td>{r.added}</td><td>{r.changed}</td><td>{r.retired}</td>
                <td>{r.clients_synced}{r.clients_failed > 0 && <span className="text-red-700"> ({r.clients_failed} failed)</span>}</td>
              </tr>
            ))}
            {runs.data?.length === 0 && <tr><td colSpan={6} className="p-2 text-slate-500">No syncs yet.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ConnectForm() {
  const qc = useQueryClient();
  const [kind, setKind] = useState<"ninjaone" | "hudu">("ninjaone");
  const [name, setName] = useState("");
  const [url, setUrl] = useState("https://app.ninjarmm.com");
  const [creds, setCreds] = useState<Record<string, string>>({});
  const [config, setConfig] = useState(HUDU_CONFIG);
  const connect = useMutation({
    mutationFn: () =>
      api("/integrations", {
        method: "POST",
        json: { kind, name, base_url: url, credentials: creds, config: kind === "hudu" ? JSON.parse(config) : {} },
      }),
    onSuccess: () => { setName(""); setCreds({}); qc.invalidateQueries({ queryKey: ["integrations"] }); },
  });
  return (
    <Card title="Connect a vendor">
      <form className="grid gap-3 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); connect.mutate(); }}>
        <Field label="Vendor">
          <select
            className={inputCls}
            value={kind}
            onChange={(e) => {
              const k = e.target.value as "ninjaone" | "hudu";
              setKind(k);
              setCreds({});
              setUrl(k === "ninjaone" ? "https://app.ninjarmm.com" : "https://");
            }}
          >
            <option value="ninjaone">NinjaOne</option>
            <option value="hudu">Hudu</option>
          </select>
        </Field>
        <Field label="Name"><input className={inputCls} required value={name} onChange={(e) => setName(e.target.value)} /></Field>
        <Field label="Address (https)"><input className={inputCls} required value={url} onChange={(e) => setUrl(e.target.value)} /></Field>
        {CRED_FIELDS[kind].map(([key, label]) => (
          <Field key={key} label={label}>
            <input className={inputCls} type="password" autoComplete="off" required value={creds[key] ?? ""} onChange={(e) => setCreds({ ...creds, [key]: e.target.value })} />
          </Field>
        ))}
        {kind === "hudu" && (
          <div className="col-span-full">
            <Field label="Which Hudu asset layouts to import, and the warranty field (JSON)">
              <textarea className={`${inputCls} font-mono`} rows={6} value={config} onChange={(e) => setConfig(e.target.value)} />
            </Field>
            <p className="mt-1 text-xs text-slate-500">Only layouts listed here are imported. Kinds: computer, server, network, other.</p>
          </div>
        )}
        <div className="col-span-full space-y-2">
          <ErrorMsg error={connect.error} />
          <Button type="submit" disabled={connect.isPending}>Connect</Button>
        </div>
      </form>
    </Card>
  );
}
