import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Notice, NoticeStatus, Page, SendResult, api } from "../../api";
import { can, useMe } from "../../auth";
import { money } from "../../money";
import { Button, ErrorMsg, fmt, inputCls } from "../../ui";

export function usePendingNotices() {
  return useQuery({ queryKey: ["notices", "pending"], queryFn: () => api<Page<Notice>>("/billing-notices?status=pending&limit=200"), refetchInterval: 60_000 });
}

export default function Reminders() {
  const { data: me } = useMe();
  const canWrite = can(me, "billing:write");
  const canSend = can(me, "billing:finalize");
  const qc = useQueryClient();
  const [view, setView] = useState<NoticeStatus>("pending");
  const list = useQuery({ queryKey: ["notices", view], queryFn: () => api<Page<Notice>>(`/billing-notices?status=${view}&limit=200`) });
  const [picked, setPicked] = useState<number[]>([]);
  const refresh = () => { qc.invalidateQueries({ queryKey: ["notices"] }); setPicked([]); };
  const prepare = useMutation({
    mutationFn: (what: "reminders" | "statements") => api<{ created: number }>(`/billing-notices/prepare-${what}`, { method: "POST" }),
    onSuccess: refresh,
  });
  const bulk = useMutation({ mutationFn: () => api<SendResult[]>("/billing-notices/send", { method: "POST", json: { ids: picked } }), onSuccess: refresh });
  const items = list.data?.items ?? [];
  const sendable = items.filter((n) => n.status === "pending" && !n.blocked_reason && !n.stale).map((n) => n.id);
  const failed = bulk.data?.filter((r) => !r.ok) ?? [];
  return (
    <div className="space-y-4">
      <p className="text-sm text-slate-600">
        Invoice emails, reminders and statements are <b>prepared for you, never sent automatically</b>. Read each one, edit it if you like, then approve it. Approved messages go out from the support mailbox and replies land as tickets.
      </p>
      <div className="flex flex-wrap items-center gap-2">
        {(["pending", "sent", "dismissed", "expired"] as NoticeStatus[]).map((v) => (
          <button key={v} className={`rounded px-3 py-1 text-sm ${view === v ? "bg-slate-800 text-white" : "border border-slate-300 bg-white"}`} onClick={() => setView(v)}>{v[0].toUpperCase() + v.slice(1)}</button>
        ))}
        <span className="flex-1" />
        {canWrite && <Button variant="secondary" onClick={() => prepare.mutate("reminders")}>Prepare reminders now</Button>}
        {canWrite && <Button variant="secondary" onClick={() => prepare.mutate("statements")}>Prepare monthly statements</Button>}
      </div>
      {prepare.data && <p role="status" className="text-sm text-slate-600">{prepare.data.created === 0 ? "Nothing new to prepare." : `${prepare.data.created} prepared.`}</p>}
      <ErrorMsg error={list.error ?? prepare.error ?? bulk.error} />
      {failed.length > 0 && <p role="alert" className="rounded bg-red-50 px-3 py-2 text-sm text-red-700">Not sent: {failed.map((f) => `#${f.id} ${f.error}`).join("; ")}</p>}
      {view === "pending" && canSend && items.length > 0 && (
        <div className="flex gap-2 text-sm">
          <Button variant="secondary" onClick={() => setPicked(picked.length === sendable.length ? [] : sendable)}>{picked.length === sendable.length ? "Clear selection" : "Select all ready"}</Button>
          <Button disabled={picked.length === 0} onClick={() => bulk.mutate()}>Send {picked.length} selected</Button>
        </div>
      )}
      {items.length === 0 && !list.isLoading && <p className="text-sm text-slate-500">{view === "pending" ? "Nothing waiting for review." : `No ${view} notices.`}</p>}
      {items.map((n) => (
        <NoticeCard key={n.id} n={n} canWrite={canWrite} canSend={canSend} picked={picked.includes(n.id)} onPick={(on) => setPicked(on ? [...picked, n.id] : picked.filter((x) => x !== n.id))} onChanged={refresh} />
      ))}
    </div>
  );
}

function NoticeCard({ n, canWrite, canSend, picked, onPick, onChanged }: { n: Notice; canWrite: boolean; canSend: boolean; picked: boolean; onPick: (on: boolean) => void; onChanged: () => void }) {
  const [subject, setSubject] = useState<string | null>(null);
  const [body, setBody] = useState<string | null>(null);
  const [reason, setReason] = useState<string | null>(null);
  const pending = n.status === "pending";
  const dirty = subject !== null || body !== null;
  const post = (action: string, json?: object) => api<Notice>(`/billing-notices/${n.id}/${action}`, { method: "POST", json });
  const save = useMutation({ mutationFn: () => api(`/billing-notices/${n.id}`, { method: "PATCH", json: { ...(subject !== null ? { subject } : {}), ...(body !== null ? { body_text: body } : {}) } }), onSuccess: () => { setSubject(null); setBody(null); onChanged(); } });
  const refreshIt = useMutation({ mutationFn: () => post("refresh"), onSuccess: () => { setSubject(null); setBody(null); onChanged(); } });
  const send = useMutation({ mutationFn: () => post("send"), onSuccess: onChanged });
  const dismiss = useMutation({ mutationFn: () => post("dismiss", { reason }), onSuccess: onChanged });
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-center gap-2">
        {pending && canSend && <input type="checkbox" aria-label={`Select ${n.organization_name}`} disabled={!!n.blocked_reason || n.stale} checked={picked} onChange={(e) => onPick(e.target.checked)} />}
        <h3 className="font-semibold">{n.organization_name}</h3>
        <span className="rounded bg-slate-100 px-2 text-xs">{n.kind === "statement" ? "Statement" : n.kind === "invoice" ? "Invoice" : n.manual ? "Reminder (manual)" : `Reminder: ${n.stage_name}`}</span>
        <span className="text-sm text-slate-600">{money(n.total_due_cents)} · {n.invoices.length} invoice{n.invoices.length === 1 ? "" : "s"}</span>
        <span className="flex-1" />
        <span className="text-xs text-slate-500">{n.status === "pending" ? `prepared ${fmt(n.created_at)}` : `${n.status} ${fmt(n.decided_at)}${n.email_status ? ` · email ${n.email_status}` : ""}`}</span>
      </div>
      {n.blocked_reason && <p role="alert" className="mt-2 rounded bg-amber-50 px-3 py-2 text-sm text-amber-900">Blocked: {n.blocked_reason}</p>}
      {n.stale && pending && <p role="alert" className="mt-2 rounded bg-amber-50 px-3 py-2 text-sm text-amber-900">Balances have changed since this was prepared. Refresh it before sending (this rewrites the text from the template).</p>}
      {n.dismiss_reason && <p className="mt-2 text-sm text-slate-600">Dismissed: {n.dismiss_reason}</p>}
      <p className="mt-2 text-sm text-slate-600">To: {n.to_emails.length ? n.to_emails.join(", ") : "nobody"}</p>
      <ul className="mt-1 text-xs text-slate-500">
        {n.invoices.map((i) => <li key={i.invoice_id}>{i.number} · due {i.due_date} · {i.days_past_due} days late · {money(i.balance_cents)}{i.new_stage ? " · new stage" : ""}</li>)}
      </ul>
      {pending && canWrite ? (
        <div className="mt-2 space-y-2">
          <input aria-label="Subject" className={inputCls} value={subject ?? n.subject} onChange={(e) => setSubject(e.target.value)} />
          <textarea aria-label="Message" className={inputCls + " font-mono"} rows={10} value={body ?? n.body_text} onChange={(e) => setBody(e.target.value)} />
        </div>
      ) : (
        <details className="mt-2 text-sm"><summary className="cursor-pointer">{n.subject}</summary><pre className="mt-1 whitespace-pre-wrap font-sans text-slate-700">{n.body_text}</pre></details>
      )}
      <ErrorMsg error={save.error ?? refreshIt.error ?? send.error ?? dismiss.error} />
      {pending && (
        <div className="mt-2 flex flex-wrap items-center gap-2">
          {canWrite && dirty && <Button variant="secondary" onClick={() => save.mutate()}>Save edits</Button>}
          {canWrite && <Button variant="secondary" onClick={() => refreshIt.mutate()}>Refresh</Button>}
          {canSend && <Button disabled={dirty || !!n.blocked_reason || n.stale} title={dirty ? "Save your edits first" : undefined} onClick={() => send.mutate()}>Approve &amp; send</Button>}
          {canSend && reason === null && <Button variant="danger" onClick={() => setReason("")}>Dismiss</Button>}
          {canSend && reason !== null && (
            <span className="flex gap-2"><input aria-label="Dismiss reason" className={inputCls} placeholder="Why? (required)" value={reason} onChange={(e) => setReason(e.target.value)} /><Button variant="danger" disabled={reason.trim().length < 3} onClick={() => dismiss.mutate()}>Confirm dismiss</Button></span>
          )}
        </div>
      )}
    </section>
  );
}
