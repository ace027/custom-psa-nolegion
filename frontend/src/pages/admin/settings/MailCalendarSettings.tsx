import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { AppSettings, MailStatus, api } from "../../../api";
import { can, useMe } from "../../../auth";
import { getCalendarSyncStatus, schedulingKeys } from "../../../scheduling/api";
import { ageMinutes, isStale } from "../../../scheduling/board";
import { Button, Card, ErrorMsg, Field, fmt, inputCls } from "../../../ui";

export default function MailCalendarSettings() {
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold tracking-tight">Mail and calendar</h1>
      <MailCard />
      <OutlookSyncCard />
      <AppointmentEmailsCard />
      <EmailAutomationCard />
    </div>
  );
}

function MailCard() {
  const q = useQuery({ queryKey: ["mail-status"], queryFn: () => api<MailStatus>("/mail/status"), refetchInterval: 30_000 });
  const s = q.data;
  return (
    <Card title="Mailbox connector">
      <ErrorMsg error={q.error} />
      {s && (
        <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm sm:grid-cols-4">
          <dt className="text-slate-500">Status</dt>
          <dd className={s.configured ? (s.last_error ? "text-red-700" : "text-green-700") : "text-amber-700"}>
            {!s.configured ? "Not configured" : s.last_error ? "Error" : "Working"}
          </dd>
          <dt className="text-slate-500">Mailbox</dt><dd>{s.mailbox ?? "—"}</dd>
          <dt className="text-slate-500">Billing mail is sent from</dt><dd>{s.accounting_mailbox ?? s.mailbox ?? "—"}</dd>
          <dt className="text-slate-500">Worker last seen</dt>
          <dd className={!s.worker_seen_at || Date.now() - new Date(s.worker_seen_at).getTime() > 5 * 60_000 ? "text-red-700" : ""}>{s.worker_seen_at ? fmt(s.worker_seen_at) : "never (is the worker container running?)"}</dd>
          <dt className="text-slate-500">Last poll</dt><dd>{fmt(s.last_poll_at)}</dd>
          <dt className="text-slate-500">Last success</dt><dd>{fmt(s.last_success_at)}</dd>
          <dt className="text-slate-500">Emails ingested</dt><dd>{s.messages_ingested}</dd>
          <dt className="text-slate-500">Outbound pending / failed</dt><dd>{s.outbound_pending} / {s.outbound_failed}</dd>
          <dt className="text-slate-500">Tickets needing triage</dt><dd>{s.tickets_needing_triage}</dd>
        </dl>
      )}
      {s?.last_error && <p className="mt-2 rounded bg-red-50 p-2 text-sm text-red-700">{fmt(s.last_error_at)}: {s.last_error}</p>}
      {s?.last_send_error && (
        <div role="alert" className="mt-2 rounded border border-red-600 p-2 text-sm text-red-700">
          <b>Last send failure</b> ({fmt(s.last_send_error_at)}): {s.last_send_error}
        </div>
      )}
      <AccountingSender />
      {s && !s.configured && <p className="mt-2 text-sm text-slate-600">Email-to-ticket is off until the mailbox is configured. See docs/MAIL_SETUP.md.</p>}
    </Card>
  );
}

function AccountingSender() {
  const qc = useQueryClient();
  const { data: me } = useMe();
  const q = useQuery({ queryKey: ["lookup", "settings"], queryFn: () => api<AppSettings>("/settings") });
  const [value, setValue] = useState<string | null>(null);
  const save = useMutation({
    mutationFn: () => api("/settings", { method: "PATCH", json: { accounting_mailbox: (value ?? "").trim() || null } }),
    onSuccess: () => { setValue(null); qc.invalidateQueries({ queryKey: ["lookup"] }); qc.invalidateQueries({ queryKey: ["mail-status"] }); },
  });
  if (!q.data || !can(me, "config:manage")) return null;
  return (
    <div className="mt-3 border-t border-slate-200 pt-3">
      <Field label="Accounting sender address">
        <input className={inputCls} type="email" placeholder="accounting@yourmsp.com" value={value ?? q.data.accounting_mailbox ?? ""} onChange={(e) => setValue(e.target.value)} />
      </Field>
      <p className="mt-2 text-xs text-slate-500">Statements, payment reminders and invoice emails are sent from this mailbox. Leave empty to send them from the support mailbox. It must be added to the mail app's scope, see docs/MAIL_SETUP.md, Accounting mailbox.</p>
      <ErrorMsg error={save.error} />
      {value !== null && <div className="mt-2"><Button onClick={() => save.mutate()} disabled={save.isPending}>Save</Button></div>}
    </div>
  );
}

export function OutlookSyncCard() {
  const qc = useQueryClient();
  const { data: me } = useMe();
  const isAdmin = me?.role === "admin";
  const q = useQuery({ queryKey: schedulingKeys.syncStatus(), queryFn: getCalendarSyncStatus, enabled: can(me, "schedule:read"), retry: false, refetchInterval: 60_000 });
  const save = useMutation({
    mutationFn: (outlook_sync_enabled: boolean) => api("/settings", { method: "PATCH", json: { outlook_sync_enabled } }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: schedulingKeys.all });
      qc.invalidateQueries({ queryKey: ["lookup"] });
    },
  });
  if (!can(me, "schedule:read")) return null;
  const s = q.data;
  const now = new Date();
  return (
    <Card title="Outlook calendar sync">
      <ErrorMsg error={q.error} />
      {q.isLoading && <p className="text-sm text-slate-500">Loading…</p>}
      {s && (
        <div className="space-y-2 text-sm">
          {isAdmin ? (
            <label className="flex min-h-[44px] items-center gap-2">
              <input type="checkbox" className="h-5 w-5" checked={s.enabled} disabled={save.isPending} onChange={(e) => save.mutate(e.target.checked)} />
              Push appointments to techs' Outlook calendars and show their Outlook busy time on the dispatch board
            </label>
          ) : (
            <p>Outlook sync is <b>{s.enabled ? "on" : "off"}</b>. Only an admin can change this.</p>
          )}
          <dl className="grid grid-cols-2 gap-x-4 gap-y-1 sm:grid-cols-4">
            <dt className="text-slate-500">Waiting to sync</dt><dd>{s.pending}</dd>
            <dt className="text-slate-500">Failed</dt><dd className={s.failed > 0 ? "font-semibold text-red-700" : ""}>{s.failed}</dd>
            <dt className="text-slate-500">Busy time updated</dt>
            <dd className={s.enabled && isStale(s.busy_fetched_at, now) ? "text-amber-800" : ""}>
              {s.busy_fetched_at ? `${ageMinutes(s.busy_fetched_at, now)} min ago` : "never"}
            </dd>
            <dt className="text-slate-500">Busy fetch errors</dt><dd>{s.busy_errors}</dd>
          </dl>
          <p className="text-xs text-slate-500">One way, PSA to Outlook. Needs the Exchange permission steps in docs/CALENDAR_SETUP.md before it is switched on.</p>
        </div>
      )}
      <ErrorMsg error={save.error} />
    </Card>
  );
}

export function AppointmentEmailsCard() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["lookup", "settings"], queryFn: () => api<AppSettings & { appointment_emails_enabled?: boolean }>("/settings") });
  const save = useMutation({
    mutationFn: (appointment_emails_enabled: boolean) => api("/settings", { method: "PATCH", json: { appointment_emails_enabled } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["lookup"] }),
  });
  if (!q.data) return null;
  return (
    <Card title="Appointment emails">
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" role="switch" checked={q.data.appointment_emails_enabled === true} disabled={save.isPending} onChange={(e) => save.mutate(e.target.checked)} />
        Send appointment emails
      </label>
      <p className="mt-2 text-xs text-slate-500">Email the ticket contact when a client-visible appointment is booked, moved or cancelled</p>
      <ErrorMsg error={save.error} />
    </Card>
  );
}

function EmailAutomationCard() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["lookup", "settings"], queryFn: () => api<AppSettings>("/settings") });
  const [edit, setEdit] = useState<Partial<AppSettings> | null>(null);
  const save = useMutation({
    mutationFn: () => api("/settings", { method: "PATCH", json: { ...edit, escalation_email: edit?.escalation_email ?? undefined } }),
    onSuccess: () => { setEdit(null); qc.invalidateQueries({ queryKey: ["lookup"] }); },
  });
  if (!q.data) return null;
  const s = { ...q.data, ...edit };
  const upd = (p: Partial<AppSettings>) => setEdit({ ...edit, ...p });
  return (
    <Card title="Auto-acknowledgement and escalation">
      <div className="space-y-3">
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={s.auto_ack_enabled} onChange={(e) => upd({ auto_ack_enabled: e.target.checked })} />
          Email a confirmation when a known client emails in a new request
        </label>
        <p className="text-xs text-slate-500">Never sent to unknown senders, automated mail or replies; at most 3 per address per day; one per ticket. Placeholders: {"{ticket_number}"} {"{contact_name}"} {"{company}"} {"{subject}"}. The subject always keeps the [#number] tag so replies thread.</p>
        <Field label="Subject"><input className={inputCls} value={s.auto_ack_subject} onChange={(e) => upd({ auto_ack_subject: e.target.value })} /></Field>
        <Field label="Message"><textarea className={inputCls} rows={5} value={s.auto_ack_body} onChange={(e) => upd({ auto_ack_body: e.target.value })} /></Field>
        <Field label="When a ticket breaches its SLA, email this address (blank = off)">
          <input className={inputCls} type="email" value={s.escalation_email ?? ""} onChange={(e) => upd({ escalation_email: e.target.value })} />
        </Field>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={s.escalation_bump_priority} onChange={(e) => upd({ escalation_bump_priority: e.target.checked })} />
          Also raise the ticket's priority by one step
        </label>
        <p className="text-xs text-slate-500">Each ticket escalates once. Turning this on escalates tickets that are already breached.</p>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={s.csat_enabled} onChange={(e) => upd({ csat_enabled: e.target.checked })} />
          Email a satisfaction survey (1 to 5) when a ticket is first resolved
        </label>
        <p className="text-xs text-slate-500">One survey per ticket, only to the ticket's contact at a known client. Each link works once and expires after 30 days; the customer confirms on a page, so mail scanners cannot answer for them.</p>
      </div>
      <ErrorMsg error={save.error} />
      {edit && <div className="mt-2"><Button onClick={() => save.mutate()}>Save</Button></div>}
    </Card>
  );
}
