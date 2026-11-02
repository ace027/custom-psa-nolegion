import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { AppSettings, Stage, api, crmApi } from "../../../api";
import { Button, Card, ErrorMsg, Field, inputCls } from "../../../ui";

export default function SalesSettings() {
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold tracking-tight">Sales</h1>
      <SalesCard />
      <StagesCard />
    </div>
  );
}

function SalesCard() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["lookup", "settings"], queryFn: () => api<AppSettings>("/settings") });
  const [days, setDays] = useState<string | null>(null);
  const [email, setEmail] = useState<string | null>(null);
  const [bad, setBad] = useState("");
  const save = useMutation({
    mutationFn: (json: { renewal_reminder_days: number[]; renewal_email: string }) => api("/settings", { method: "PATCH", json }),
    onSuccess: () => { setDays(null); setEmail(null); qc.invalidateQueries(); },
  });
  const s = q.data;
  if (!s) return null;
  const shownDays = days ?? (s.renewal_reminder_days ?? []).join(", ");
  const shownEmail = email ?? s.renewal_email ?? "";
  const submit = () => {
    const parts = shownDays.split(/[,\s]+/).filter(Boolean).map(Number);
    if (parts.length < 1 || parts.length > 5 || parts.some((n) => !Number.isInteger(n) || n < 1 || n > 365) || new Set(parts).size !== parts.length) {
      return setBad("Enter 1 to 5 different whole numbers of days between 1 and 365, for example 90, 60, 30.");
    }
    setBad("");
    save.mutate({ renewal_reminder_days: parts, renewal_email: shownEmail.trim() });
  };
  return (
    <Card title="Sales">
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Renewal reminder days before an agreement ends (comma list)">
          <input className={inputCls} value={shownDays} onChange={(e) => setDays(e.target.value)} placeholder="90, 60, 30" />
        </Field>
        <Field label="Renewal reminder email (blank = none)">
          <input type="email" className={inputCls} value={shownEmail} onChange={(e) => setEmail(e.target.value)} />
        </Field>
      </div>
      {bad && <p role="alert" className="mt-2 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{bad}</p>}
      <ErrorMsg error={save.error} />
      {(days !== null || email !== null) && <div className="mt-2"><Button onClick={submit} disabled={save.isPending}>Save</Button></div>}
    </Card>
  );
}

function StagesCard() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["crm", "stages"], queryFn: crmApi.stages });
  const [form, setForm] = useState({ name: "", position: "10", pct: "50", kind: "open" });
  const [bad, setBad] = useState("");
  const refresh = () => qc.invalidateQueries({ queryKey: ["crm"] });
  const add = useMutation({
    mutationFn: (j: { name: string; position: number; probability_bp: number; kind: Stage["kind"] }) => crmApi.createStage(j),
    onSuccess: () => { setForm({ name: "", position: "10", pct: "50", kind: "open" }); refresh(); },
  });
  const patch = useMutation({
    mutationFn: ({ id, json }: { id: number; json: { name?: string; position?: number; probability_bp?: number; active?: boolean } }) => crmApi.updateStage(id, json),
    onSuccess: refresh,
  });
  const submit = () => {
    const pos = Number(form.position);
    const pct = Number(form.pct);
    if (!form.name.trim() || !Number.isInteger(pos) || pos < 0 || !(pct >= 0 && pct <= 100)) return setBad("Give a name, a position of 0 or more and a probability from 0 to 100.");
    setBad("");
    add.mutate({ name: form.name.trim(), position: pos, probability_bp: Math.round(pct * 100), kind: form.kind as Stage["kind"] });
  };
  return (
    <Card title="Sales pipeline stages">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-slate-200 text-left text-slate-500">
            <th scope="col" className="py-1">Name</th><th scope="col">Probability %</th><th scope="col">Kind</th><th scope="col">Position</th><th scope="col">Active</th>
          </tr>
        </thead>
        <tbody>
          {(q.data ?? []).map((st) => <StageRow key={st.id} st={st} onSave={(json) => patch.mutate({ id: st.id, json })} />)}
        </tbody>
      </table>
      <div className="mt-3 grid gap-2 sm:grid-cols-[1fr_6rem_6rem_8rem_auto] sm:items-end">
        <Field label="New stage name"><input className={inputCls} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
        <Field label="Position"><input className={inputCls} type="number" min={0} value={form.position} onChange={(e) => setForm({ ...form, position: e.target.value })} /></Field>
        <Field label="Probability %"><input className={inputCls} type="number" min={0} max={100} value={form.pct} onChange={(e) => setForm({ ...form, pct: e.target.value })} /></Field>
        <Field label="Kind">
          <select className={inputCls} value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}>
            <option value="open">Open</option><option value="won">Won</option><option value="lost">Lost</option>
          </select>
        </Field>
        <Button onClick={submit} disabled={add.isPending}>Add stage</Button>
      </div>
      {bad && <p role="alert" className="mt-2 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{bad}</p>}
      <ErrorMsg error={q.error ?? add.error ?? patch.error} />
      <p className="mt-2 text-xs text-slate-500">The kind of a stage is fixed once created. Deactivate a stage to hide its column; opportunities in it keep their stage.</p>
    </Card>
  );
}

function StageRow({ st, onSave }: { st: Stage; onSave: (json: { name?: string; position?: number; probability_bp?: number; active?: boolean }) => void }) {
  const [name, setName] = useState(st.name);
  const [pct, setPct] = useState(String(st.probability_bp / 100));
  const [pos, setPos] = useState(String(st.position));
  const dirty = name !== st.name || Number(pct) * 100 !== st.probability_bp || Number(pos) !== st.position;
  return (
    <tr className="border-b border-slate-100">
      <td className="py-1"><input aria-label={`Name of stage ${st.name}`} className={inputCls} value={name} onChange={(e) => setName(e.target.value)} /></td>
      <td><input aria-label={`Probability of ${st.name}`} className={inputCls + " w-24"} type="number" min={0} max={100} value={pct} onChange={(e) => setPct(e.target.value)} /></td>
      <td className="capitalize">{st.kind}</td>
      <td><input aria-label={`Position of ${st.name}`} className={inputCls + " w-20"} type="number" min={0} value={pos} onChange={(e) => setPos(e.target.value)} /></td>
      <td>
        <label className="flex items-center gap-1"><input type="checkbox" checked={st.active} onChange={(e) => onSave({ active: e.target.checked })} />Active</label>
      </td>
      <td className="text-right">
        {dirty && <Button variant="secondary" onClick={() => onSave({ name: name.trim(), probability_bp: Math.round(Number(pct) * 100), position: Number(pos) })}>Save</Button>}
      </td>
    </tr>
  );
}
