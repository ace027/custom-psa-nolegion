import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  Webhook,
  createWebhook,
  listWebhookDeliveries,
  listWebhooks,
  retryWebhookDelivery,
  rotateWebhookSecret,
  testWebhook,
  updateWebhook,
} from "../api";
import { Button, Card, ErrorMsg, Field, fmt, inputCls } from "../ui";

const EVENTS: [string, string][] = [
  ["ticket.created", "A ticket is created"],
  ["ticket.assigned", "A ticket is assigned"],
  ["ticket.status_changed", "A ticket's status changes"],
  ["ticket.priority_changed", "A ticket's priority changes"],
  ["ticket.customer_reply", "A customer replies"],
  ["ticket.sla_breached", "A ticket breaches its SLA"],
  ["rmm_alert.opened", "A monitoring alert opens a ticket"],
  ["rmm_alert.cleared", "A monitoring alert clears"],
];
const label = (e: string) => EVENTS.find(([k]) => k === e)?.[1] ?? e;
const STATUS_STYLE = { pending: "text-amber-700", delivered: "text-green-700", failed: "text-red-700" };

function Deliveries({ hook }: { hook: Webhook }) {
  const qc = useQueryClient();
  const list = useQuery({ queryKey: ["webhook-deliveries", hook.id], queryFn: () => listWebhookDeliveries(hook.id) });
  const retry = useMutation({
    mutationFn: (id: number) => retryWebhookDelivery(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["webhook-deliveries", hook.id] }),
  });
  return (
    <div className="mt-2 rounded border border-slate-200 p-2">
      <ErrorMsg error={list.error ?? retry.error} />
      <table className="w-full text-left text-sm">
        <thead className="border-b border-slate-200 text-slate-500">
          <tr><th className="p-1">Event</th><th>Status</th><th>Attempts</th><th>Last result</th><th>Next attempt</th><th /></tr>
        </thead>
        <tbody>
          {list.data?.map((d) => (
            <tr key={d.id} className="border-b border-slate-100">
              <td className="p-1">{d.event_type}</td>
              <td className={STATUS_STYLE[d.status]}>{d.status}</td>
              <td>{d.attempts}</td>
              <td>{d.last_error ?? (d.last_status_code ? `HTTP ${d.last_status_code}` : "—")}</td>
              <td>{d.status === "pending" ? fmt(d.next_attempt_at) : "—"}</td>
              <td>
                {d.status !== "delivered" && (
                  <Button variant="secondary" onClick={() => retry.mutate(d.id)} aria-label={`Retry delivery ${d.id}`}>Retry</Button>
                )}
              </td>
            </tr>
          ))}
          {list.data?.length === 0 && <tr><td colSpan={6} className="p-2 text-slate-500">Nothing sent yet.</td></tr>}
        </tbody>
      </table>
    </div>
  );
}

export default function Webhooks() {
  const qc = useQueryClient();
  const list = useQuery({ queryKey: ["webhooks"], queryFn: listWebhooks });
  const [name, setName] = useState("");
  const [kind, setKind] = useState("generic");
  const [url, setUrl] = useState("");
  const [events, setEvents] = useState<string[]>([]);
  const [secret, setSecret] = useState<{ name: string; value: string } | null>(null);
  const [copied, setCopied] = useState(false);
  const [open, setOpen] = useState<number | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const refresh = () => qc.invalidateQueries({ queryKey: ["webhooks"] });
  const reveal = (n: string, v: string) => {
    setSecret({ name: n, value: v });
    setCopied(false);
  };
  const create = useMutation({
    mutationFn: () => createWebhook({ name, kind, url, events }),
    onSuccess: (r) => {
      reveal(r.endpoint.name, r.secret);
      setName("");
      setUrl("");
      setEvents([]);
      refresh();
    },
  });
  const toggle = useMutation({
    mutationFn: (h: Webhook) => updateWebhook(h.id, { enabled: !h.enabled }),
    onSuccess: refresh,
  });
  const rotate = useMutation({
    mutationFn: (h: Webhook) => rotateWebhookSecret(h.id),
    onSuccess: (r) => {
      reveal(r.endpoint.name, r.secret);
      refresh();
    },
  });
  const test = useMutation({
    mutationFn: (h: Webhook) => testWebhook(h.id),
    onSuccess: (_r, h) => {
      setNote(`Test sent to "${h.name}". It goes out within a minute; check the delivery log.`);
      qc.invalidateQueries({ queryKey: ["webhook-deliveries", h.id] });
    },
  });
  const onRotate = (h: Webhook) => {
    if (window.confirm(`Replace the signing secret for "${h.name}"? The old one stops working immediately.`)) rotate.mutate(h);
  };
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold tracking-tight">Webhooks</h1>
      <p className="text-sm text-slate-600">
        Send ticket and alert events to Microsoft Teams, n8n or any tool that accepts a signed HTTPS request. Each message carries facts and a link,
        never the ticket text.
      </p>
      {secret && (
        <Card title={`Signing secret for ${secret.name}`}>
          <p role="alert" className="mb-2 rounded bg-amber-50 px-3 py-2 text-sm text-amber-800">Store this secret now. It will not be shown again.</p>
          <div className="flex gap-2">
            <input aria-label="Signing secret" readOnly className={`${inputCls} font-mono`} value={secret.value} onFocus={(e) => e.currentTarget.select()} />
            <Button variant="secondary" onClick={() => { navigator.clipboard?.writeText(secret.value); setCopied(true); }}>{copied ? "Copied" : "Copy"}</Button>
            <Button variant="secondary" onClick={() => setSecret(null)}>Dismiss</Button>
          </div>
        </Card>
      )}
      {note && <p role="status" className="rounded bg-green-50 px-3 py-2 text-sm text-green-800">{note}</p>}
      <Card title="Endpoints">
        <ErrorMsg error={list.error ?? toggle.error ?? rotate.error ?? test.error} />
        <ul className="space-y-3">
          {list.data?.map((h) => (
            <li key={h.id} className="rounded border border-slate-200 p-3">
              <div className="flex flex-wrap items-center gap-3">
                <strong>{h.name}</strong>
                <span className="text-sm text-slate-500">{h.kind === "teams" ? "Microsoft Teams" : "Generic"}</span>
                <span className="font-mono text-sm">{h.url_preview}</span>
                {h.consecutive_failures > 0 && (
                  <span className="rounded bg-red-100 px-2 py-0.5 text-xs text-red-800">{h.consecutive_failures} failed in a row</span>
                )}
                <label className="ml-auto flex items-center gap-1 text-sm">
                  <input type="checkbox" checked={h.enabled} disabled={toggle.isPending} onChange={() => toggle.mutate(h)} aria-label={`Enabled ${h.name}`} />
                  Enabled
                </label>
              </div>
              <p className="mt-1 text-sm text-slate-600">{h.events.map(label).join("; ")}</p>
              <p className="text-xs text-slate-500">Last success: {fmt(h.last_success_at)}</p>
              <div className="mt-2 flex gap-2">
                <Button variant="secondary" onClick={() => test.mutate(h)} aria-label={`Send test to ${h.name}`}>Send test</Button>
                <Button variant="secondary" onClick={() => onRotate(h)} aria-label={`Rotate secret for ${h.name}`}>Rotate secret</Button>
                <Button variant="secondary" onClick={() => setOpen(open === h.id ? null : h.id)} aria-label={`Deliveries for ${h.name}`}>
                  {open === h.id ? "Hide deliveries" : "Deliveries"}
                </Button>
              </div>
              {open === h.id && <Deliveries hook={h} />}
            </li>
          ))}
          {list.data?.length === 0 && <li className="text-sm text-slate-500">No webhooks yet.</li>}
        </ul>
      </Card>
      <Card title="Add a webhook">
        <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); create.mutate(); }}>
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="Name"><input className={inputCls} required maxLength={100} value={name} onChange={(e) => setName(e.target.value)} /></Field>
            <Field label="Type">
              <select className={inputCls} value={kind} onChange={(e) => setKind(e.target.value)}>
                <option value="generic">Generic</option>
                <option value="teams">Microsoft Teams</option>
              </select>
            </Field>
            <Field label="URL"><input className={inputCls} required type="url" placeholder="https://" value={url} onChange={(e) => setUrl(e.target.value)} /></Field>
          </div>
          <fieldset>
            <legend className="mb-1 text-sm font-medium">Send when</legend>
            <div className="grid gap-1 sm:grid-cols-2">
              {EVENTS.map(([k, text]) => (
                <label key={k} className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={events.includes(k)} onChange={(e) => setEvents(e.target.checked ? [...events, k] : events.filter((x) => x !== k))} />
                  {text}
                </label>
              ))}
            </div>
          </fieldset>
          <ErrorMsg error={create.error} />
          <Button type="submit" disabled={create.isPending || events.length === 0}>Add webhook</Button>
        </form>
      </Card>
    </div>
  );
}
