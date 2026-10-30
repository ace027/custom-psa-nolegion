import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { REPORT_NAMES, ReportName, ReportSchedule, ScheduleInput, User, api, reportsApi } from "../../api";
import { can, useMe } from "../../auth";
import { Button, Card, ErrorMsg, Field, fmt, inputCls } from "../../ui";

const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const REPORT_LABEL: Record<ReportName, string> = { sla: "SLA performance", utilisation: "Utilisation", aging: "Receivables aging", profitability: "Profitability" };
// Admin and billing hold report:read; the server re-checks every recipient.
const holdsReportRead = (u: User) => u.is_active && (u.role === "admin" || u.role === "billing");

interface Draft {
  name: string;
  report: ReportName;
  frequency: "weekly" | "monthly";
  weekday: number;
  day_of_month: number;
  recipients: number[];
  active: boolean;
}
const blank: Draft = { name: "", report: "sla", frequency: "weekly", weekday: 0, day_of_month: 1, recipients: [], active: true };
const toDraft = (s: ReportSchedule): Draft => ({
  name: s.name, report: s.report, frequency: s.frequency, weekday: s.weekday ?? 0, day_of_month: s.day_of_month ?? 1, recipients: s.recipient_user_ids, active: s.active,
});
const toInput = (d: Draft): ScheduleInput => ({
  name: d.name.trim(),
  report: d.report,
  frequency: d.frequency,
  ...(d.frequency === "weekly" ? { weekday: d.weekday } : { day_of_month: d.day_of_month }),
  recipient_user_ids: d.recipients,
  active: d.active,
});
const when = (s: ReportSchedule) => (s.frequency === "weekly" ? `Weekly, ${WEEKDAYS[s.weekday ?? 0]}` : `Monthly, day ${s.day_of_month}`);

export default function ReportSchedules() {
  const { data: me } = useMe();
  const write = can(me, "config:manage");
  const qc = useQueryClient();
  const list = useQuery({ queryKey: ["report-schedules"], queryFn: reportsApi.schedules });
  const users = useQuery({ queryKey: ["users"], queryFn: () => api<User[]>("/users") });
  const [editing, setEditing] = useState<number | "new" | null>(null);
  const [runsFor, setRunsFor] = useState<number | null>(null);
  const opener = useRef<string>("sched-new");
  const refocus = useRef(false);
  const open = (target: number | "new") => { opener.current = target === "new" ? "sched-new" : `sched-edit-${target}`; setEditing(target); };
  const close = () => { refocus.current = true; setEditing(null); };
  const done = () => { close(); qc.invalidateQueries({ queryKey: ["report-schedules"] }); };
  useEffect(() => {
    if (editing !== null || !refocus.current) return;
    refocus.current = false;
    (document.getElementById(opener.current) ?? document.getElementById("sched-new"))?.focus();
  }, [editing]);
  const busy = editing !== null;
  const lock = busy ? { disabled: true, "aria-disabled": true, title: "Save or cancel the open form first" } : {};
  const toggle = useMutation({
    mutationFn: (s: ReportSchedule) => reportsApi.updateSchedule(s.id, { active: !s.active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["report-schedules"] }),
  });
  const names = new Map((users.data ?? []).map((u) => [u.id, u.display_name]));
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold tracking-tight">Scheduled reports</h1>
      <p className="text-sm text-slate-600">
        The worker emails each report once per period as a CSV to staff who hold report:read. Weekly reports cover the previous Monday to Sunday; monthly reports cover the previous calendar month. Schedules are deactivated, not deleted.
      </p>
      <ErrorMsg error={list.error ?? toggle.error ?? users.error} />
      {users.isLoading && <p role="status" className="text-sm text-slate-500">Loading users...</p>}
      {write && <Button id="sched-new" {...lock} onClick={() => open("new")}>New schedule</Button>}
      {write && editing === "new" && <ScheduleForm initial={blank} users={users.data ?? []} onDone={done} onCancel={close} />}
      <Card title="Schedules">
        {list.isLoading && <div role="status" aria-busy="true" className="space-y-2"><div className="h-10 animate-pulse rounded bg-slate-100" /><div className="h-10 animate-pulse rounded bg-slate-100" /><span className="sr-only">Loading schedules...</span></div>}
        {list.data && list.data.length === 0 && <p className="text-sm text-slate-500">No scheduled reports yet.</p>}
        <ul className="divide-y divide-slate-100 text-sm">
          {list.data?.map((s) => (
            <li key={s.id} className="py-2">
              {editing === s.id ? (
                <ScheduleForm id={s.id} initial={toDraft(s)} users={users.data ?? []} onDone={done} onCancel={close} />
              ) : (
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <b>{s.name}</b> <span className="text-slate-500">{REPORT_LABEL[s.report] ?? s.report} · {when(s)} · {s.active ? "active" : "inactive"}</span>
                    <div className="text-xs text-slate-500">To: {s.recipient_user_ids.length === 0 ? "No recipients" : s.recipient_user_ids.map((id) => names.get(id) ?? `user ${id}`).join(", ")}</div>
                  </div>
                  <div className="flex gap-2">
                    <Button variant="secondary" aria-label={`Runs for ${s.name}`} aria-expanded={runsFor === s.id} aria-controls={`runs-${s.id}`} onClick={() => setRunsFor(runsFor === s.id ? null : s.id)}>Runs</Button>
                    {write && <Button variant="secondary" id={`sched-edit-${s.id}`} aria-label={`Edit ${s.name}`} {...lock} onClick={() => open(s.id)}>Edit</Button>}
                    {write && <Button variant="secondary" aria-label={`${s.active ? "Deactivate" : "Activate"} ${s.name}`} disabled={toggle.isPending} onClick={() => toggle.mutate(s)}>{s.active ? "Deactivate" : "Activate"}</Button>}
                  </div>
                </div>
              )}
              {runsFor === s.id && <Runs id={s.id} />}
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}

function Runs({ id }: { id: number }) {
  const q = useQuery({ queryKey: ["report-schedule-runs", id], queryFn: () => reportsApi.scheduleRuns(id) });
  return (
    <div id={`runs-${id}`} className="mt-2 rounded-lg bg-slate-50 p-3">
      <ErrorMsg error={q.error} />
      {q.isLoading && <p role="status" className="text-xs text-slate-500">Loading runs...</p>}
      {q.data && q.data.length === 0 && <p className="text-xs text-slate-500">Not run yet.</p>}
      {q.data && q.data.length > 0 && (
        <table className="w-full text-left text-xs">
          <thead className="text-slate-500"><tr><th>Period</th><th>Status</th><th>Recipients</th><th>Detail</th><th>Recorded</th></tr></thead>
          <tbody>
            {q.data.map((r) => (
              <tr key={r.id}><td>{r.period_start} to {r.period_end}</td><td>{r.status}</td><td>{r.recipients.join(", ")}</td><td>{r.detail ?? ""}</td><td>{fmt(r.created_at)}</td></tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function ScheduleForm({ id, initial, users, onDone, onCancel }: { id?: number; initial: Draft; users: User[]; onDone: () => void; onCancel: () => void }) {
  const [d, setD] = useState<Draft>(initial);
  const nameRef = useRef<HTMLInputElement>(null);
  useEffect(() => { nameRef.current?.focus(); }, []);
  const save = useMutation({
    mutationFn: () => (id === undefined ? reportsApi.createSchedule(toInput(d)) : reportsApi.updateSchedule(id, toInput(d))),
    onSuccess: onDone,
  });
  const eligible = users.filter((u) => holdsReportRead(u) || d.recipients.includes(u.id));
  const setDay = (v: string) => setD({ ...d, day_of_month: Math.min(28, Math.max(1, Number(v) || 1)) });
  return (
    <form className="space-y-3 rounded-lg border border-slate-200 p-3" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
      <div className="flex flex-wrap items-end gap-3">
        <Field label="Name"><input ref={nameRef} className={inputCls} required maxLength={200} value={d.name} onChange={(e) => setD({ ...d, name: e.target.value })} /></Field>
        <Field label="Report">
          <select className={inputCls} value={d.report} onChange={(e) => setD({ ...d, report: e.target.value as ReportName })}>
            {REPORT_NAMES.map((r) => <option key={r} value={r}>{REPORT_LABEL[r]}</option>)}
          </select>
        </Field>
        <Field label="Frequency">
          <select className={inputCls} value={d.frequency} onChange={(e) => setD({ ...d, frequency: e.target.value as Draft["frequency"] })}>
            <option value="weekly">Weekly</option>
            <option value="monthly">Monthly</option>
          </select>
        </Field>
        {d.frequency === "weekly" ? (
          <Field label="Weekday">
            <select className={inputCls} value={d.weekday} onChange={(e) => setD({ ...d, weekday: Number(e.target.value) })}>
              {WEEKDAYS.map((w, i) => <option key={w} value={i}>{w}</option>)}
            </select>
          </Field>
        ) : (
          <Field label="Day of month (1-28)"><input className={inputCls} type="number" min={1} max={28} value={d.day_of_month} onChange={(e) => setDay(e.target.value)} /></Field>
        )}
      </div>
      <fieldset>
        <legend className="mb-1 text-sm font-medium text-slate-700">Recipients (staff with report:read)</legend>
        {eligible.length === 0 && <p className="text-sm text-slate-500">No eligible recipients</p>}
        <div className="flex flex-wrap gap-3 text-sm">
          {eligible.map((u) => (
            <label key={u.id} className="flex items-center gap-1">
              <input type="checkbox" checked={d.recipients.includes(u.id)} onChange={(e) => setD({ ...d, recipients: e.target.checked ? [...d.recipients, u.id] : d.recipients.filter((x) => x !== u.id) })} />
              {u.display_name}
            </label>
          ))}
        </div>
      </fieldset>
      <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={d.active} onChange={(e) => setD({ ...d, active: e.target.checked })} />Active</label>
      <ErrorMsg error={save.error} />
      {(!d.name.trim() || d.recipients.length === 0) && <p className="text-xs text-slate-500">{!d.name.trim() ? "Enter a name. " : ""}{d.recipients.length === 0 ? "Select at least one recipient." : ""}</p>}
      <div className="flex gap-2">
        <Button type="submit" disabled={save.isPending || d.recipients.length === 0 || !d.name.trim()}>{id === undefined ? "Create schedule" : "Save schedule"}</Button>
        <Button type="button" variant="secondary" onClick={onCancel}>Cancel</Button>
      </div>
    </form>
  );
}
