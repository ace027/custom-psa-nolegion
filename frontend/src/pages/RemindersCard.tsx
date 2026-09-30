import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { AppSettings, ReminderStage, api } from "../api";
import { Button, Card, ErrorMsg, Field, inputCls } from "../ui";

const HELP =
  "Placeholders: {client} {company} {contact_name} {invoice_list} {invoice_count} {total_due} {oldest_days_late} {as_of} {overdue_total} {credit}";

export default function RemindersCard() {
  const qc = useQueryClient();
  const stages = useQuery({ queryKey: ["reminder-stages"], queryFn: () => api<ReminderStage[]>("/billing/reminder-stages") });
  const settings = useQuery({ queryKey: ["lookup", "settings"], queryFn: () => api<AppSettings>("/settings") });
  const s = settings.data;
  const [prefs, setPrefs] = useState<Partial<AppSettings>>({});
  const savePrefs = useMutation({
    mutationFn: () => api("/settings", { method: "PATCH", json: prefs }),
    onSuccess: () => { setPrefs({}); qc.invalidateQueries({ queryKey: ["lookup"] }); },
  });
  if (!s) return null;
  const val = <K extends keyof AppSettings>(k: K) => (k in prefs ? prefs[k] : s[k]) as AppSettings[K];
  const set = (p: Partial<AppSettings>) => setPrefs({ ...prefs, ...p });
  return (
    <Card title="Payment reminders and statements">
      <p className="mb-2 text-sm text-slate-600">Nothing here sends by itself: the worker only <b>prepares</b> notices, and a person approves each one on Billing → Reminders. Each stage is issued at most once per invoice.</p>
      <div className="grid gap-3 sm:grid-cols-3">
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={val("auto_prepare_reminders")} onChange={(e) => set({ auto_prepare_reminders: e.target.checked })} />Prepare reminders daily</label>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={val("auto_prepare_statements")} onChange={(e) => set({ auto_prepare_statements: e.target.checked })} />Prepare statements monthly</label>
        <Field label="Minimum days between reminders to a client"><input className={inputCls} type="number" min={0} max={90} value={val("reminder_min_gap_days")} onChange={(e) => set({ reminder_min_gap_days: Number(e.target.value) })} /></Field>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={val("auto_prepare_invoice_emails")} onChange={(e) => set({ auto_prepare_invoice_emails: e.target.checked })} />Prepare an invoice email when an invoice is finalized</label>
        <Field label="Invoice email subject"><input className={inputCls} value={val("invoice_email_subject")} onChange={(e) => set({ invoice_email_subject: e.target.value })} /></Field>
        <div className="sm:col-span-2"><Field label="Invoice email body (also {invoice_number} {invoice_total} {due_date})"><textarea className={inputCls + " font-mono"} rows={5} value={val("invoice_email_body")} onChange={(e) => set({ invoice_email_body: e.target.value })} /></Field></div>
        <Field label="Statement email subject"><input className={inputCls} value={val("statement_subject")} onChange={(e) => set({ statement_subject: e.target.value })} /></Field>
        <div className="sm:col-span-2"><Field label="Statement email body"><textarea className={inputCls + " font-mono"} rows={6} value={val("statement_body")} onChange={(e) => set({ statement_body: e.target.value })} /></Field></div>
      </div>
      <p className="mt-1 text-xs text-slate-500">{HELP}</p>
      <ErrorMsg error={savePrefs.error} />
      {Object.keys(prefs).length > 0 && <div className="mt-2"><Button onClick={() => savePrefs.mutate()}>Save</Button></div>}
      <h3 className="mt-4 text-sm font-medium">Reminder schedule</h3>
      {stages.data?.map((st) => <StageEditor key={st.id} st={st} />)}
    </Card>
  );
}

function StageEditor({ st }: { st: ReminderStage }) {
  const qc = useQueryClient();
  const [e, setE] = useState<Partial<ReminderStage>>({});
  const save = useMutation({
    mutationFn: () => api(`/billing/reminder-stages/${st.id}`, { method: "PATCH", json: e }),
    onSuccess: () => { setE({}); qc.invalidateQueries({ queryKey: ["reminder-stages"] }); },
  });
  const v = { ...st, ...e };
  return (
    <details className="mt-2 rounded border border-slate-200 p-2 text-sm">
      <summary className="cursor-pointer">{v.name} · {v.days_past_due} days past due{v.enabled ? "" : " (off)"}</summary>
      <div className="mt-2 grid gap-2 sm:grid-cols-3">
        <Field label="Name"><input className={inputCls} value={v.name} onChange={(x) => setE({ ...e, name: x.target.value })} /></Field>
        <Field label="Days past due"><input className={inputCls} type="number" min={0} max={365} value={v.days_past_due} onChange={(x) => setE({ ...e, days_past_due: Number(x.target.value) })} /></Field>
        <label className="flex items-end gap-2 pb-2"><input type="checkbox" checked={v.enabled} onChange={(x) => setE({ ...e, enabled: x.target.checked })} />Enabled</label>
        <div className="sm:col-span-3"><Field label="Subject"><input className={inputCls} value={v.subject} onChange={(x) => setE({ ...e, subject: x.target.value })} /></Field></div>
        <div className="sm:col-span-3"><Field label="Body"><textarea className={inputCls + " font-mono"} rows={8} value={v.body} onChange={(x) => setE({ ...e, body: x.target.value })} /></Field></div>
      </div>
      <ErrorMsg error={save.error} />
      {Object.keys(e).length > 0 && <div className="mt-2"><Button onClick={() => save.mutate()}>Save stage</Button></div>}
    </details>
  );
}
