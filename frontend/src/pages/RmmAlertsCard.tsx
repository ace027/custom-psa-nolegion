import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { Integration, RmmAlertState, api, listRmmAlerts, requestAlertPoll } from "../api";
import { Button, Card, ErrorMsg, Field, fmt, inputCls } from "../ui";

const SEVERITIES = ["NONE", "MINOR", "MODERATE", "MAJOR", "CRITICAL"];
const RULES = [
  ["resolve_if_untouched", "Resolve if nobody has worked the ticket"],
  ["always_resolve", "Always resolve"],
  ["note_only", "Add a note only"],
] as const;
const SEV_STYLE: Record<string, string> = {
  CRITICAL: "bg-red-100 text-red-800",
  MAJOR: "bg-orange-100 text-orange-800",
  MODERATE: "bg-amber-100 text-amber-800",
  MINOR: "bg-slate-100 text-slate-700",
};
const RESOLUTION: Record<string, string> = { resolved: "Ticket resolved", noted: "Note added", superseded: "Superseded", none: "—" };

export function relTime(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return "";
  const mins = Math.max(0, Math.round((now - new Date(iso).getTime()) / 60000));
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const h = Math.round(mins / 60);
  if (h < 48) return `${h} h ago`;
  return `${Math.round(h / 24)} days ago`;
}

export default function RmmAlertsCard({ integration: i, onSaved }: { integration: Integration; onSaved: () => void }) {
  const cfg = i.config ?? {};
  const [enabled, setEnabled] = useState(cfg.alerts_enabled === true);
  const [severity, setSeverity] = useState(typeof cfg.alert_min_severity === "string" ? cfg.alert_min_severity : "MODERATE");
  const [rule, setRule] = useState(typeof cfg.alert_clear_rule === "string" ? cfg.alert_clear_rule : "resolve_if_untouched");
  const [minutes, setMinutes] = useState(String(typeof cfg.alert_poll_minutes === "number" ? cfg.alert_poll_minutes : 5));
  const [state, setState] = useState<RmmAlertState>("open");
  const alertsOn = cfg.alerts_enabled === true;

  const alerts = useQuery({ queryKey: ["rmm-alerts", i.id, state], queryFn: () => listRmmAlerts(i.id, state) });
  const save = useMutation({
    mutationFn: () =>
      api(`/integrations/${i.id}`, {
        method: "PATCH",
        json: {
          config: {
            ...cfg,
            alerts_enabled: enabled,
            alert_min_severity: severity,
            alert_clear_rule: rule,
            alert_poll_minutes: Number(minutes),
          },
        },
      }),
    onSuccess: onSaved,
  });
  const poll = useMutation({ mutationFn: () => requestAlertPoll(i.id), onSuccess: onSaved });

  return (
    <Card title="Alerts to tickets">
      <form className="grid gap-3 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
        <label className="flex items-center gap-2 text-sm sm:col-span-2">
          <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
          Create tickets from alerts
        </label>
        <Field label="Minimum severity">
          <select className={inputCls} value={severity} onChange={(e) => setSeverity(e.target.value)}>
            {SEVERITIES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </Field>
        <Field label="When an alert clears">
          <select className={inputCls} value={rule} onChange={(e) => setRule(e.target.value)}>
            {RULES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </Field>
        <Field label="Check every (minutes)">
          <input className={inputCls} type="number" min={1} max={60} required value={minutes} onChange={(e) => setMinutes(e.target.value)} />
        </Field>
        <div className="col-span-full flex flex-wrap gap-2">
          <Button type="submit" disabled={save.isPending}>Save alert settings</Button>
          <Button type="button" variant="secondary" disabled={!alertsOn || poll.isPending} onClick={() => poll.mutate()}>Check now</Button>
        </div>
      </form>
      <div className="mt-2 space-y-1 text-sm">
        <p className="text-slate-600">
          {i.alerts_polled_at ? `Last checked ${relTime(i.alerts_polled_at)}` : "Not checked yet"}
          {i.alerts_requested && <span className="ml-2 text-blue-700">Check queued</span>}
        </p>
        {i.alerts_last_error && (
          <p role="alert" className="break-words rounded bg-red-50 px-3 py-2 text-red-700">{i.alerts_last_error}</p>
        )}
      </div>
      <ErrorMsg error={save.error ?? poll.error} />
      <div className="mt-4 border-t border-slate-200 pt-3">
        <div className="mb-2 flex items-center justify-between">
          <h3 className="text-sm font-medium">Alerts</h3>
          <select aria-label="Alert filter" className="rounded-lg border border-slate-300 bg-surface px-2 py-1 text-sm" value={state} onChange={(e) => setState(e.target.value as RmmAlertState)}>
            <option value="open">Open</option>
            <option value="cleared">Cleared</option>
            <option value="all">All</option>
          </select>
        </div>
        {alerts.isLoading && <p className="text-sm text-slate-500">Loading…</p>}
        <ErrorMsg error={alerts.error} />
        {alerts.data && (
          <div className="overflow-x-auto">
            <table aria-label="RMM alerts" className="w-full text-left text-sm">
              <thead className="border-b border-slate-200 text-slate-500">
                <tr>
                  {["Severity", "Client", "Device", "Message", "Times", "First seen", "Cleared", "Resolution", "Ticket"].map((h) => (
                    <th key={h} scope="col" className="px-2 py-1">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {alerts.data.map((a) => (
                  <tr key={a.id} className="border-b border-slate-100 align-top">
                    <td className="px-2 py-1"><span className={`rounded px-1.5 text-xs ${SEV_STYLE[a.severity] ?? "bg-slate-100 text-slate-700"}`}>{a.severity}</span></td>
                    <td className="px-2 py-1">{a.organization_name}</td>
                    <td className="px-2 py-1">{a.asset_name}</td>
                    <td className="break-words px-2 py-1">{a.message}</td>
                    <td className="px-2 py-1">{a.occurrences}</td>
                    <td className="px-2 py-1">{fmt(a.first_seen_at)}</td>
                    <td className="px-2 py-1">{a.cleared_at ? fmt(a.cleared_at) : "—"}</td>
                    <td className="px-2 py-1">{a.resolution ? (RESOLUTION[a.resolution] ?? a.resolution) : "—"}</td>
                    <td className="px-2 py-1">{a.ticket_id ? <Link className="text-blue-700 hover:underline" to={`/tickets/${a.ticket_id}`}>#{a.ticket_number}</Link> : "—"}</td>
                  </tr>
                ))}
                {alerts.data.length === 0 && (
                  <tr><td colSpan={9} className="px-2 py-2 text-slate-500">{state === "open" ? "No open alerts." : "No alerts."}</td></tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </Card>
  );
}
