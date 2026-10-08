import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Agreement, DeviceClass, Organization, Quote, Survey, SurveyApp, SurveyDevice, api } from "../../api";
import { can, useMe } from "../../auth";
import { money } from "../../money";
import { Button, Card, ErrorMsg, Field, inputCls } from "../../ui";
import { Badge } from "./QuotesList";

interface Form {
  user_count: string;
  site_count: string;
  notes: string;
  devices: SurveyDevice[];
  apps: SurveyApp[];
}
const CLASS_LABEL: Record<DeviceClass, string> = { workstation: "Workstation", server: "Server", network: "Network", other: "Other" };
const blankDevice = (device_class: DeviceClass): SurveyDevice => ({ device_class, label: "", make_model: "", serial: "", warranty_end: null, warranty_status: "unknown", priced: true, notes: null });
const draftKey = (id: string) => `psa-survey-draft-${id}`;

// The draft lives in the browser so a dropped connection on site loses nothing; it is
// cleared as soon as the server has the same data. Storage can be blocked: never rely on it.
function readDraft(id: string): Form | null {
  try { const raw = localStorage.getItem(draftKey(id)); return raw ? (JSON.parse(raw) as Form) : null; } catch { return null; }
}
function writeDraft(id: string, form: Form | null) {
  try { form ? localStorage.setItem(draftKey(id), JSON.stringify(form)) : localStorage.removeItem(draftKey(id)); } catch { /* ignore */ }
}

export default function SurveyPage() {
  const id = useParams().id as string;
  const qc = useQueryClient();
  const survey = useQuery({ queryKey: ["survey", id], queryFn: () => api<Survey>(`/surveys/${id}`) });
  const [form, setForm] = useState<Form | null>(null);
  const [restored, setRestored] = useState(false);
  const s = survey.data;
  useEffect(() => {
    if (!s || form) return;
    const server: Form = { user_count: String(s.user_count), site_count: String(s.site_count), notes: s.notes ?? "", devices: s.devices, apps: s.apps };
    const draft = s.status === "completed" ? null : readDraft(id);
    setRestored(!!draft);
    setForm(draft ?? server);
  }, [s, form, id]);
  const locked = s?.status === "completed";
  const update = (next: Form) => { setForm(next); writeDraft(id, next); };
  const body = (f: Form) => ({
    user_count: Number(f.user_count) || 0,
    site_count: Number(f.site_count) || 0,
    notes: f.notes || null,
    devices: f.devices.map(({ id: _i, ...d }) => ({ ...d, warranty_end: d.warranty_end || null })),
    apps: f.apps.map(({ id: _i, ...a }) => a),
  });
  const save = useMutation({
    mutationFn: (f: Form) => api<Survey>(`/surveys/${id}`, { method: "PUT", json: body(f) }),
    onSuccess: (saved) => { writeDraft(id, null); setRestored(false); qc.setQueryData(["survey", id], saved); qc.invalidateQueries({ queryKey: ["surveys"] }); },
  });
  const complete = useMutation({
    mutationFn: async () => { await save.mutateAsync(form!); return api<Survey>(`/surveys/${id}/complete`, { method: "POST" }); },
    onSuccess: (done) => { qc.setQueryData(["survey", id], done); qc.invalidateQueries({ queryKey: ["surveys"] }); },
  });
  if (!s || !form) return <ErrorMsg error={survey.error} />;
  const priced = form.devices.filter((d) => d.priced);
  const out = priced.filter((d) => d.warranty_status !== "in_warranty").length;
  const setDevice = (i: number, patch: Partial<SurveyDevice>) => update({ ...form, devices: form.devices.map((d, j) => (j === i ? { ...d, ...patch } : d)) });
  const setApp = (i: number, patch: Partial<SurveyApp>) => update({ ...form, apps: form.apps.map((a, j) => (j === i ? { ...a, ...patch } : a)) });
  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <p><Link className="text-sm text-blue-700 hover:underline" to="/quotes">← Quotes</Link></p>
      <div className="flex items-center gap-2">
        <h1 className="text-2xl font-bold tracking-tight">Site survey: {s.organization_name}</h1>
        <Badge status={s.status} />
      </div>
      {locked && <p className="rounded bg-slate-100 px-3 py-2 text-sm">This survey is completed and can no longer be edited. It is the evidence behind the quote.</p>}
      {restored && <p role="status" className="rounded bg-amber-50 px-3 py-2 text-sm text-amber-900">Restored unsaved changes from this device. Press Save to send them to the server.</p>}
      <fieldset disabled={locked} className="space-y-4">
        <Card title="Environment">
          <div className="grid grid-cols-2 gap-3">
            <Field label="Users"><input className={inputCls} inputMode="numeric" value={form.user_count} onChange={(e) => update({ ...form, user_count: e.target.value })} /></Field>
            <Field label="Sites"><input className={inputCls} inputMode="numeric" value={form.site_count} onChange={(e) => update({ ...form, site_count: e.target.value })} /></Field>
          </div>
          <div className="mt-3"><Field label="Notes (Microsoft 365, backups, security, anything unusual)"><textarea className={inputCls} rows={4} value={form.notes} onChange={(e) => update({ ...form, notes: e.target.value })} /></Field></div>
        </Card>
        <Card title={`Devices (${priced.length} priced, ${out} out of warranty or unknown)`}>
          <div className="space-y-3">
            {form.devices.map((d, i) => (
              <div key={i} className="space-y-2 rounded border border-slate-200 p-3" aria-label={`Device ${i + 1}`}>
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                  <Field label="Type"><select className={inputCls} value={d.device_class} onChange={(e) => setDevice(i, { device_class: e.target.value as DeviceClass })}>{Object.entries(CLASS_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></Field>
                  <Field label="Name"><input className={inputCls} value={d.label ?? ""} onChange={(e) => setDevice(i, { label: e.target.value })} /></Field>
                  <Field label="Make / model"><input className={inputCls} value={d.make_model ?? ""} onChange={(e) => setDevice(i, { make_model: e.target.value })} /></Field>
                  <Field label="Serial"><input className={inputCls} value={d.serial ?? ""} onChange={(e) => setDevice(i, { serial: e.target.value })} /></Field>
                </div>
                <div className="grid grid-cols-2 items-end gap-2 sm:grid-cols-4">
                  <Field label="Warranty ends"><input aria-label="Warranty ends" className={inputCls} type="date" value={d.warranty_end ?? ""} onChange={(e) => setDevice(i, { warranty_end: e.target.value || null })} /></Field>
                  <Field label="Warranty (if no date)">
                    <select className={inputCls} disabled={!!d.warranty_end} value={d.warranty_status} onChange={(e) => setDevice(i, { warranty_status: e.target.value as SurveyDevice["warranty_status"] })}>
                      <option value="unknown">Unknown</option><option value="in_warranty">In warranty</option><option value="out_of_warranty">Out of warranty</option>
                    </select>
                  </Field>
                  <label className="flex items-center gap-1 pb-2 text-sm"><input type="checkbox" checked={d.priced} onChange={(e) => setDevice(i, { priced: e.target.checked })} />Covered by the contract</label>
                  <button type="button" className="pb-2 text-left text-sm text-red-700 hover:underline" onClick={() => update({ ...form, devices: form.devices.filter((_, j) => j !== i) })}>Remove</button>
                </div>
              </div>
            ))}
            {form.devices.length === 0 && <p className="text-sm text-slate-500">No devices yet.</p>}
            <div className="flex flex-wrap gap-2">
              {(Object.keys(CLASS_LABEL) as DeviceClass[]).map((c) => <Button key={c} type="button" variant="secondary" onClick={() => update({ ...form, devices: [...form.devices, blankDevice(c)] })}>+ {CLASS_LABEL[c]}</Button>)}
            </div>
          </div>
        </Card>
        <Card title="Line-of-business applications">
          <div className="space-y-3">
            {form.apps.map((a, i) => (
              <div key={i} className="grid grid-cols-2 items-end gap-2 rounded border border-slate-200 p-3 sm:grid-cols-4" aria-label={`Application ${i + 1}`}>
                <Field label="Application"><input className={inputCls} value={a.name} onChange={(e) => setApp(i, { name: e.target.value })} /></Field>
                <Field label="Vendor"><input className={inputCls} value={a.vendor ?? ""} onChange={(e) => setApp(i, { vendor: e.target.value })} /></Field>
                <label className="flex items-center gap-1 pb-2 text-sm"><input type="checkbox" checked={a.legacy} onChange={(e) => setApp(i, { legacy: e.target.checked })} />Legacy / unsupported</label>
                <button type="button" className="pb-2 text-left text-sm text-red-700 hover:underline" onClick={() => update({ ...form, apps: form.apps.filter((_, j) => j !== i) })}>Remove</button>
              </div>
            ))}
            <Button type="button" variant="secondary" onClick={() => update({ ...form, apps: [...form.apps, { name: "", vendor: "", legacy: false, notes: null }] })}>+ Application</Button>
          </div>
        </Card>
      </fieldset>
      <ErrorMsg error={save.error ?? complete.error} />
      {!locked && (
        <div className="sticky bottom-0 flex gap-2 border-t border-slate-200 bg-surface/95 py-3">
          <Button type="button" disabled={save.isPending} onClick={() => save.mutate(form)}>Save</Button>
          <Button type="button" variant="secondary" disabled={complete.isPending} onClick={() => { if (window.confirm("Complete this survey? It cannot be edited afterwards.")) complete.mutate(); }}>Save and complete</Button>
          {save.isSuccess && !save.isPending && <span role="status" className="self-center text-sm text-green-700">Saved.</span>}
        </div>
      )}
      {locked && <PriceIt survey={s} />}
    </div>
  );
}

function PriceIt({ survey }: { survey: Survey }) {
  const { data: me } = useMe();
  const nav = useNavigate();
  const quotes = useQuery({ queryKey: ["quotes", "org", survey.organization_id], queryFn: () => api<Quote[]>(`/quotes?organization_id=${survey.organization_id}`) });
  const org = useQuery({ queryKey: ["org", survey.organization_id], queryFn: () => api<Organization>(`/organizations/${survey.organization_id}`) });
  const ags = useQuery({ queryKey: ["agreements", "org", survey.organization_id], queryFn: () => api<Agreement[]>(`/agreements?organization_id=${survey.organization_id}`), enabled: can(me, "billing:read") });
  const flat = (ags.data ?? []).filter((a) => a.type === "flat" && !a.end_date);
  const now = new Date();
  const nextMonth = new Date(now.getFullYear(), now.getMonth() + 1, 1);
  const iso = `${nextMonth.getFullYear()}-${String(nextMonth.getMonth() + 1).padStart(2, "0")}-01`;
  const [agreementId, setAgreementId] = useState("");
  const [eff, setEff] = useState(iso);
  const qc = useQueryClient();
  const create = useMutation({
    mutationFn: () => api<Quote>(`/surveys/${survey.id}/quote`, { method: "POST", json: agreementId ? { kind: "reprice", agreement_id: Number(agreementId), effective_date: eff } : { kind: "new" } }),
    onSuccess: (q) => { qc.invalidateQueries({ queryKey: ["quotes"] }); nav(`/quotes/${q.id}`); },
  });
  if (!can(me, "quote:write")) return null;
  const open = quotes.data?.find((q) => q.survey_id === survey.id && ["draft", "needs_approval", "approved", "sent"].includes(q.status));
  if (open) return <Card title="Quote"><p className="text-sm">This survey has an open quote: <Link className="text-blue-700 hover:underline" to={`/quotes/${open.id}`}>{open.number}</Link> ({money(open.final_price_cents)}/month).</p></Card>;
  return (
    <Card title="Price this survey">
      <div className="space-y-3">
        {org.data?.status === "active" && flat.length > 0 && (
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Reprice an existing flat-fee agreement?">
              <select className={inputCls} value={agreementId} onChange={(e) => setAgreementId(e.target.value)}>
                <option value="">No, this is a new contract</option>
                {flat.map((a) => <option key={a.id} value={a.id}>{a.name} ({money(a.unit_price_cents)}/month)</option>)}
              </select>
            </Field>
            {agreementId && <Field label="New price starts (first of a month)"><input className={inputCls} type="date" value={eff} onChange={(e) => setEff(e.target.value)} /></Field>}
          </div>
        )}
        <ErrorMsg error={create.error} />
        <Button onClick={() => create.mutate()} disabled={create.isPending}>Create quote</Button>
      </div>
    </Card>
  );
}
