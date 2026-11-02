import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { CannedResponse, CustomFieldDef, FieldType, Lookup, Priority, Queue, TicketStatusRow, api } from "../../../api";
import { Button, Card, ErrorMsg, Field, inputCls } from "../../../ui";

export default function TicketSettings() {
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold tracking-tight">Tickets</h1>
      <SimpleList title="Queues" path="queues" defaults />
      <SimpleList title="Categories" path="categories" />
      <SimpleList title="Work types" path="work-types" />
      <PrioritiesCard />
      <StatusesCard />
      <TicketTypesCard />
      <CannedCard />
    </div>
  );
}

export function SimpleList({ title, path, defaults }: { title: string; path: string; defaults?: boolean }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["cfg", path], queryFn: () => api<(Lookup & Partial<Queue>)[]>(`/${path}?include_archived=true`) });
  const [name, setName] = useState("");
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["cfg", path] });
    qc.invalidateQueries({ queryKey: ["lookup"] });
  };
  const add = useMutation({ mutationFn: () => api(`/${path}`, { method: "POST", json: { name } }), onSuccess: () => { setName(""); refresh(); } });
  const act = useMutation({
    mutationFn: ({ id, action, json }: { id: number; action?: string; json?: object }) =>
      action ? api(`/${path}/${id}/${action}`, { method: "POST" }) : api(`/${path}/${id}`, { method: "PATCH", json }),
    onSuccess: refresh,
  });
  return (
    <Card title={title}>
      <ul className="divide-y divide-slate-100 text-sm">
        {q.data?.map((x) => (
          <li key={x.id} className="flex items-center justify-between py-1.5">
            <span className={x.archived_at ? "text-slate-400 line-through" : ""}>{x.name}{x.is_default && <b className="ml-2 text-xs text-blue-700">default</b>}</span>
            <span className="flex gap-2">
              {defaults && !x.is_default && !x.archived_at && <Button variant="secondary" onClick={() => act.mutate({ id: x.id, json: { is_default: true } })}>Make default</Button>}
              {!x.is_default && <Button variant="secondary" onClick={() => act.mutate({ id: x.id, action: x.archived_at ? "unarchive" : "archive" })}>{x.archived_at ? "Restore" : "Archive"}</Button>}
            </span>
          </li>
        ))}
      </ul>
      <ErrorMsg error={add.error ?? act.error} />
      <form className="mt-2 flex items-end gap-2" onSubmit={(e) => { e.preventDefault(); add.mutate(); }}>
        <Field label="Add"><input className={inputCls} required value={name} onChange={(e) => setName(e.target.value)} /></Field>
        <Button type="submit">Add</Button>
      </form>
    </Card>
  );
}

function PrioritiesCard() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["cfg", "priorities"], queryFn: () => api<Priority[]>("/priorities?include_archived=true") });
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["cfg", "priorities"] });
    qc.invalidateQueries({ queryKey: ["lookup"] });
  };
  const save = useMutation({ mutationFn: ({ id, json }: { id: number; json: object }) => api(`/priorities/${id}`, { method: "PATCH", json }), onSuccess: refresh });
  const [n, setN] = useState({ name: "", rank: "5", fr: "", res: "" });
  const add = useMutation({
    mutationFn: () => api("/priorities", { method: "POST", json: { name: n.name, rank: Number(n.rank), first_response_minutes: n.fr ? Number(n.fr) : null, resolution_minutes: n.res ? Number(n.res) : null } }),
    onSuccess: () => { setN({ name: "", rank: "5", fr: "", res: "" }); refresh(); },
  });
  const num = (v: string) => (v === "" ? null : Number(v));
  return (
    <Card title="Priorities and SLA targets (business minutes)">
      <table className="w-full text-left text-sm">
        <thead className="text-slate-500"><tr><th>Name</th><th>Rank</th><th>First response</th><th>Resolution</th><th /></tr></thead>
        <tbody>
          {q.data?.map((p) => (
            <tr key={p.id} className="border-t border-slate-100">
              <td className={p.archived_at ? "text-slate-400 line-through" : ""}>{p.name}{p.is_default && <b className="ml-2 text-xs text-blue-700">default</b>}</td>
              <td>{p.rank}</td>
              <td><input aria-label={`${p.name} first response`} className={inputCls + " w-24"} type="number" defaultValue={p.first_response_minutes ?? ""} onBlur={(e) => num(e.target.value) !== p.first_response_minutes && save.mutate({ id: p.id, json: { first_response_minutes: num(e.target.value) } })} /></td>
              <td><input aria-label={`${p.name} resolution`} className={inputCls + " w-24"} type="number" defaultValue={p.resolution_minutes ?? ""} onBlur={(e) => num(e.target.value) !== p.resolution_minutes && save.mutate({ id: p.id, json: { resolution_minutes: num(e.target.value) } })} /></td>
              <td>{!p.is_default && !p.archived_at && <Button variant="secondary" onClick={() => save.mutate({ id: p.id, json: { is_default: true } })}>Make default</Button>}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <ErrorMsg error={save.error ?? add.error} />
      <form className="mt-3 flex flex-wrap items-end gap-2" onSubmit={(e) => { e.preventDefault(); add.mutate(); }}>
        <Field label="Name"><input className={inputCls} required value={n.name} onChange={(e) => setN({ ...n, name: e.target.value })} /></Field>
        <div className="w-20"><Field label="Rank"><input className={inputCls} type="number" min={1} value={n.rank} onChange={(e) => setN({ ...n, rank: e.target.value })} /></Field></div>
        <div className="w-32"><Field label="First response"><input className={inputCls} type="number" min={1} value={n.fr} onChange={(e) => setN({ ...n, fr: e.target.value })} /></Field></div>
        <div className="w-32"><Field label="Resolution"><input className={inputCls} type="number" min={1} value={n.res} onChange={(e) => setN({ ...n, res: e.target.value })} /></Field></div>
        <Button type="submit">Add priority</Button>
      </form>
    </Card>
  );
}

function CannedCard() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["cfg", "canned-responses"], queryFn: () => api<CannedResponse[]>("/canned-responses?include_archived=true") });
  const [f, setF] = useState({ name: "", body: "" });
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["cfg", "canned-responses"] });
    qc.invalidateQueries({ queryKey: ["canned"] });
  };
  const add = useMutation({ mutationFn: () => api("/canned-responses", { method: "POST", json: f }), onSuccess: () => { setF({ name: "", body: "" }); refresh(); } });
  const act = useMutation({ mutationFn: ({ id, action }: { id: number; action: string }) => api(`/canned-responses/${id}/${action}`, { method: "POST" }), onSuccess: refresh });
  return (
    <Card title="Canned responses">
      <p className="mb-2 text-sm text-slate-600">Reusable replies for the note box. Placeholders: <code>{"{{contact_name}}"}</code>, <code>{"{{ticket_number}}"}</code>.</p>
      <ul className="divide-y divide-slate-100 text-sm">
        {q.data?.map((x) => (
          <li key={x.id} className="flex items-start justify-between gap-2 py-1.5">
            <span className={x.archived_at ? "text-slate-400 line-through" : ""}><b>{x.name}</b><span className="block whitespace-pre-wrap text-slate-600">{x.body}</span></span>
            <Button variant="secondary" onClick={() => act.mutate({ id: x.id, action: x.archived_at ? "unarchive" : "archive" })}>{x.archived_at ? "Restore" : "Archive"}</Button>
          </li>
        ))}
      </ul>
      <ErrorMsg error={add.error ?? act.error} />
      <form className="mt-2 space-y-2" onSubmit={(e) => { e.preventDefault(); add.mutate(); }}>
        <Field label="Name"><input className={inputCls} required value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
        <Field label="Text"><textarea className={inputCls} rows={3} required value={f.body} onChange={(e) => setF({ ...f, body: e.target.value })} /></Field>
        <Button type="submit">Add response</Button>
      </form>
    </Card>
  );
}

const BEHAVIOR_LABEL: Record<string, string> = {
  new: "counts as New",
  open: "counts as Open",
  waiting_on_customer: "pauses the SLA clock (waiting)",
  resolved: "stops the SLA clock (resolved)",
  closed: "stops the SLA clock (closed)",
};

function StatusesCard() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["cfg", "ticket-statuses"], queryFn: () => api<TicketStatusRow[]>("/ticket-statuses?include_archived=true") });
  const [f, setF] = useState({ name: "", behavior: "open" });
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["cfg", "ticket-statuses"] });
    qc.invalidateQueries({ queryKey: ["lookup"] });
  };
  const add = useMutation({ mutationFn: () => api("/ticket-statuses", { method: "POST", json: f }), onSuccess: () => { setF({ ...f, name: "" }); refresh(); } });
  const act = useMutation({ mutationFn: ({ id, action }: { id: number; action: string }) => api(`/ticket-statuses/${id}/${action}`, { method: "POST" }), onSuccess: refresh });
  const rename = useMutation({ mutationFn: ({ id, name }: { id: number; name: string }) => api(`/ticket-statuses/${id}`, { method: "PATCH", json: { name } }), onSuccess: refresh });
  return (
    <Card title="Ticket statuses">
      <p className="mb-2 text-sm text-slate-600">Each status behaves like one of the five built-in states, chosen when you create it and fixed afterwards, so SLA clocks, reopening on customer replies, and the dashboard keep working.</p>
      <ul className="divide-y divide-slate-100 text-sm">
        {q.data?.map((x) => (
          <li key={x.id} className="flex items-center justify-between gap-2 py-1.5">
            <span className={x.archived_at ? "text-slate-400 line-through" : ""}>
              <b>{x.name}</b> <span className="text-slate-500">{BEHAVIOR_LABEL[x.behavior]}</span>
            </span>
            <span className="flex gap-2">
              <Button variant="secondary" onClick={() => { const name = window.prompt("Rename status", x.name); if (name) rename.mutate({ id: x.id, name }); }}>Rename</Button>
              <Button variant="secondary" onClick={() => act.mutate({ id: x.id, action: x.archived_at ? "unarchive" : "archive" })}>{x.archived_at ? "Restore" : "Archive"}</Button>
            </span>
          </li>
        ))}
      </ul>
      <ErrorMsg error={add.error ?? act.error ?? rename.error} />
      <form className="mt-2 flex flex-wrap items-end gap-3" onSubmit={(e) => { e.preventDefault(); add.mutate(); }}>
        <Field label="Name"><input className={inputCls} required value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
        <Field label="Behaves like">
          <select className={inputCls} value={f.behavior} onChange={(e) => setF({ ...f, behavior: e.target.value })}>
            {Object.entries(BEHAVIOR_LABEL).map(([k, v]) => <option key={k} value={k}>{k.replace(/_/g, " ")} ({v})</option>)}
          </select>
        </Field>
        <Button type="submit">Add status</Button>
      </form>
    </Card>
  );
}

const FIELD_TYPES: FieldType[] = ["text", "number", "date", "dropdown", "checkbox"];

function TicketTypesCard() {
  const qc = useQueryClient();
  const types = useQuery({ queryKey: ["cfg", "ticket-types"], queryFn: () => api<Lookup[]>("/ticket-types?include_archived=true") });
  const [open, setOpen] = useState<number | null>(null);
  const [name, setName] = useState("");
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["cfg"] });
    qc.invalidateQueries({ queryKey: ["lookup"] });
  };
  const add = useMutation({ mutationFn: () => api("/ticket-types", { method: "POST", json: { name } }), onSuccess: () => { setName(""); refresh(); } });
  const act = useMutation({ mutationFn: ({ id, action }: { id: number; action: string }) => api(`/ticket-types/${id}/${action}`, { method: "POST" }), onSuccess: refresh });
  const rename = useMutation({ mutationFn: ({ id, name }: { id: number; name: string }) => api(`/ticket-types/${id}`, { method: "PATCH", json: { name } }), onSuccess: refresh });
  return (
    <Card title="Ticket types and custom fields">
      <p className="mb-2 text-sm text-slate-600">A type (for example New hire) carries its own extra fields. Required fields are enforced when a ticket gets the type. Fields can be hidden but never deleted, so old tickets keep their answers.</p>
      <ul className="divide-y divide-slate-100 text-sm">
        {types.data?.map((x) => (
          <li key={x.id} className="py-1.5">
            <div className="flex items-center justify-between gap-2">
              <span className={x.archived_at ? "text-slate-400 line-through" : "font-semibold"}>{x.name}</span>
              <span className="flex gap-2">
                <Button variant="secondary" onClick={() => setOpen(open === x.id ? null : x.id)}>{open === x.id ? "Hide fields" : "Fields"}</Button>
                <Button variant="secondary" onClick={() => { const n = window.prompt("Rename type", x.name); if (n) rename.mutate({ id: x.id, name: n }); }}>Rename</Button>
                <Button variant="secondary" onClick={() => act.mutate({ id: x.id, action: x.archived_at ? "unarchive" : "archive" })}>{x.archived_at ? "Restore" : "Archive"}</Button>
              </span>
            </div>
            {open === x.id && <FieldsEditor typeId={x.id} typeArchived={!!x.archived_at} />}
          </li>
        ))}
      </ul>
      <ErrorMsg error={add.error ?? act.error ?? rename.error} />
      <form className="mt-2 flex items-end gap-3" onSubmit={(e) => { e.preventDefault(); add.mutate(); }}>
        <Field label="New type"><input className={inputCls} required value={name} onChange={(e) => setName(e.target.value)} /></Field>
        <Button type="submit">Add type</Button>
      </form>
    </Card>
  );
}

function FieldsEditor({ typeId, typeArchived }: { typeId: number; typeArchived: boolean }) {
  const qc = useQueryClient();
  const key = ["cfg", "fields", typeId];
  const q = useQuery({ queryKey: key, queryFn: () => api<CustomFieldDef[]>(`/ticket-types/${typeId}/fields?include_archived=true`) });
  const blank = { name: "", field_type: "text" as FieldType, options: "", required: false, client_visible: false };
  const [f, setF] = useState(blank);
  const refresh = () => qc.invalidateQueries({ queryKey: key });
  const add = useMutation({
    mutationFn: () => api(`/ticket-types/${typeId}/fields`, {
      method: "POST",
      json: { name: f.name, field_type: f.field_type, required: f.required, client_visible: f.client_visible, options: f.field_type === "dropdown" ? f.options.split(",").map((o) => o.trim()).filter(Boolean) : null },
    }),
    onSuccess: () => { setF(blank); refresh(); },
  });
  const patch = useMutation({ mutationFn: ({ id, json }: { id: number; json: Record<string, unknown> }) => api(`/custom-fields/${id}`, { method: "PATCH", json }), onSuccess: refresh });
  const act = useMutation({ mutationFn: ({ id, action }: { id: number; action: string }) => api(`/custom-fields/${id}/${action}`, { method: "POST" }), onSuccess: refresh });
  return (
    <div className="mt-2 rounded border border-slate-200 p-3">
      <ul className="divide-y divide-slate-100">
        {q.data?.map((d) => (
          <li key={d.id} className="flex flex-wrap items-center justify-between gap-2 py-1">
            <span className={d.archived_at ? "text-slate-400 line-through" : ""}>
              <b>{d.name}</b> <span className="text-slate-500">{d.field_type}{d.options ? ` (${d.options.join(", ")})` : ""}{d.required ? " · required" : ""}{d.client_visible ? " · shown to client" : ""}</span>
            </span>
            <span className="flex gap-2">
              <Button variant="secondary" onClick={() => patch.mutate({ id: d.id, json: { required: !d.required } })}>{d.required ? "Make optional" : "Make required"}</Button>
              <Button variant="secondary" onClick={() => patch.mutate({ id: d.id, json: { client_visible: !d.client_visible } })}>{d.client_visible ? "Hide from client" : "Show to client"}</Button>
              <Button variant="secondary" onClick={() => { const n = window.prompt("Rename field", d.name); if (n) patch.mutate({ id: d.id, json: { name: n } }); }}>Rename</Button>
              <Button variant="secondary" onClick={() => act.mutate({ id: d.id, action: d.archived_at ? "unarchive" : "archive" })}>{d.archived_at ? "Restore" : "Archive"}</Button>
            </span>
          </li>
        ))}
      </ul>
      <ErrorMsg error={add.error ?? patch.error ?? act.error} />
      {!typeArchived && (
        <form className="mt-2 flex flex-wrap items-end gap-3" onSubmit={(e) => { e.preventDefault(); add.mutate(); }}>
          <Field label="Field name"><input className={inputCls} required value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
          <Field label="Kind">
            <select className={inputCls} value={f.field_type} onChange={(e) => setF({ ...f, field_type: e.target.value as FieldType })}>
              {FIELD_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </Field>
          {f.field_type === "dropdown" && <Field label="Options (comma separated)"><input className={inputCls} required value={f.options} onChange={(e) => setF({ ...f, options: e.target.value })} /></Field>}
          <label className="flex items-center gap-1 pb-2 text-sm"><input type="checkbox" checked={f.required} onChange={(e) => setF({ ...f, required: e.target.checked })} />Required</label>
          <label className="flex items-center gap-1 pb-2 text-sm"><input type="checkbox" checked={f.client_visible} onChange={(e) => setF({ ...f, client_visible: e.target.checked })} />Show to client</label>
          <Button type="submit">Add field</Button>
        </form>
      )}
    </div>
  );
}
