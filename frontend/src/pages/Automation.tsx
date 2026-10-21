import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import {
  AutomationRule,
  Organization,
  RuleAction,
  RuleBody,
  RuleCondition,
  RuleTestResult,
  api,
  archiveRule,
  createRule,
  listRuleRuns,
  listRules,
  listWebhooks,
  testRule,
  updateRule,
} from "../api";
import { useLookups } from "../lookups";
import { Button, Card, ErrorMsg, Field, fmt, inputCls } from "../ui";

const TRIGGERS: [string, string][] = [
  ["ticket.created", "A ticket is created"],
  ["ticket.assigned", "A ticket is assigned"],
  ["ticket.status_changed", "A ticket's status changes"],
  ["ticket.priority_changed", "A ticket's priority changes"],
  ["ticket.customer_reply", "A customer replies"],
  ["ticket.sla_breached", "A ticket breaches its SLA"],
  ["rmm_alert.opened", "A monitoring alert opens a ticket"],
  ["rmm_alert.cleared", "A monitoring alert clears"],
];
const triggerLabel = (t: string) => TRIGGERS.find(([k]) => k === t)?.[1] ?? t;

const OPS: Record<string, string> = {
  eq: "is",
  ne: "is not",
  in: "is any of",
  not_in: "is none of",
  contains: "contains",
  is_empty: "is empty",
  is_not_empty: "is not empty",
};
const ID_OPS = ["eq", "ne", "in", "not_in"];
const NULLABLE_OPS = [...ID_OPS, "is_empty", "is_not_empty"];
type Kind = "org" | "queue" | "category" | "priority" | "type" | "user" | "status" | "source" | "severity" | "text";
const FIELDS: Record<string, { label: string; kind: Kind; ops: string[] }> = {
  organization_id: { label: "Client", kind: "org", ops: NULLABLE_OPS },
  queue_id: { label: "Queue", kind: "queue", ops: ID_OPS },
  category_id: { label: "Category", kind: "category", ops: NULLABLE_OPS },
  priority_id: { label: "Priority", kind: "priority", ops: ID_OPS },
  ticket_type_id: { label: "Ticket type", kind: "type", ops: NULLABLE_OPS },
  assignee_id: { label: "Assigned to", kind: "user", ops: NULLABLE_OPS },
  status: { label: "Status", kind: "status", ops: ID_OPS },
  source: { label: "Source", kind: "source", ops: ID_OPS },
  subject: { label: "Subject", kind: "text", ops: ["eq", "ne", "contains", "is_empty", "is_not_empty"] },
  alert_severity: { label: "Alert severity", kind: "severity", ops: ID_OPS },
};
const CHOICES: Record<string, [string, string][]> = {
  status: [["new", "New"], ["open", "Open"], ["waiting_on_customer", "Waiting on customer"], ["resolved", "Resolved"], ["closed", "Closed"]],
  source: [["ui", "Created by staff"], ["email", "Email"], ["portal", "Portal"], ["rmm", "Monitoring"], ["rule", "Automation"]],
  severity: [["NONE", "None"], ["MINOR", "Minor"], ["MODERATE", "Moderate"], ["MAJOR", "Major"], ["CRITICAL", "Critical"]],
};
const ACTION_TYPES: [string, string][] = [
  ["assign", "Assign to"],
  ["set_queue", "Move to queue"],
  ["set_priority", "Set priority"],
  ["escalate", "Raise priority one step"],
  ["notify", "Email a person"],
  ["webhook", "Send to a webhook"],
  ["create_ticket", "Create a related ticket"],
];
const valueless = (op: string) => op === "is_empty" || op === "is_not_empty";
const multi = (op: string) => op === "in" || op === "not_in";

interface Draft {
  id: number | null;
  name: string;
  trigger: string;
  enabled: boolean;
  position: number;
  conditions: RuleCondition[];
  actions: RuleAction[];
}
const blank = (): Draft => ({ id: null, name: "", trigger: "ticket.created", enabled: true, position: 0, conditions: [], actions: [] });

type Opt = [string, string];
function useOptions() {
  const l = useLookups();
  const orgs = useQuery({
    queryKey: ["orgs-all"],
    queryFn: () => api<Organization[] | { items: Organization[] }>("/organizations"),
  });
  const hooks = useQuery({ queryKey: ["webhooks"], queryFn: listWebhooks });
  const orgList = Array.isArray(orgs.data) ? orgs.data : (orgs.data?.items ?? []);
  const lk = (rows: { id: number; name: string }[]): Opt[] => rows.map((r) => [String(r.id), r.name]);
  const byKind: Record<string, Opt[]> = {
    org: lk(orgList),
    queue: lk(l.queues.filter((q) => !q.archived_at)),
    category: lk(l.categories.filter((c) => !c.archived_at)),
    priority: lk(l.priorities.filter((p) => !p.archived_at)),
    type: lk(l.ticketTypes.filter((t) => !t.archived_at)),
    user: l.techs.map((u) => [String(u.id), u.display_name]),
    status: CHOICES.status,
    source: CHOICES.source,
    severity: CHOICES.severity,
  };
  const endpoints: Opt[] = (Array.isArray(hooks.data) ? hooks.data : []).map((h) => [String(h.id), h.name]);
  return { byKind, endpoints };
}

const numeric = (kind: Kind) => !["status", "source", "severity", "text"].includes(kind);
const conv = (kind: Kind, v: string) => (numeric(kind) ? Number(v) : v);

function ConditionRow({
  c, i, trigger, opts, onChange, onRemove,
}: {
  c: RuleCondition; i: number; trigger: string; opts: Record<string, Opt[]>;
  onChange: (c: RuleCondition) => void; onRemove: () => void;
}) {
  const spec = FIELDS[c.field];
  const n = i + 1;
  const setField = (field: string) => onChange({ field, op: "eq", value: "" });
  const setOp = (op: string) => onChange({ ...c, op, value: valueless(op) ? undefined : multi(op) ? [] : "" });
  const fields = Object.entries(FIELDS).filter(([k]) => k !== "alert_severity" || trigger.startsWith("rmm_alert."));
  const choices = opts[spec.kind] ?? [];
  let value;
  if (valueless(c.op)) value = null;
  else if (spec.kind === "text") {
    value = <input aria-label={`Condition value ${n}`} className={inputCls} maxLength={200} value={String(c.value ?? "")} onChange={(e) => onChange({ ...c, value: e.target.value })} />;
  } else if (multi(c.op)) {
    const current = (Array.isArray(c.value) ? c.value : []).map(String);
    value = (
      <fieldset aria-label={`Condition value ${n}`} className="flex max-h-40 flex-col gap-1 overflow-y-auto rounded border border-slate-300 p-2">
        {choices.map(([k, text]) => (
          <label key={k} className="flex items-center gap-2 text-sm">
            <input
              type="checkbox" checked={current.includes(k)}
              onChange={(e) => {
                const next = e.target.checked ? [...current, k] : current.filter((x) => x !== k);
                onChange({ ...c, value: choices.filter(([ck]) => next.includes(ck)).map(([ck]) => conv(spec.kind, ck)) });
              }}
            />
            {text}
          </label>
        ))}
      </fieldset>
    );
  } else {
    value = (
      <select aria-label={`Condition value ${n}`} className={inputCls} value={c.value === "" || c.value == null ? "" : String(c.value)} onChange={(e) => onChange({ ...c, value: e.target.value === "" ? "" : conv(spec.kind, e.target.value) })}>
        <option value="">Choose…</option>
        {choices.map(([k, text]) => <option key={k} value={k}>{text}</option>)}
      </select>
    );
  }
  return (
    <div className="grid items-end gap-2 sm:grid-cols-[1fr_1fr_2fr_auto]">
      <select aria-label={`Condition field ${n}`} className={inputCls} value={c.field} onChange={(e) => setField(e.target.value)}>
        {fields.map(([k, f]) => <option key={k} value={k}>{f.label}</option>)}
      </select>
      <select aria-label={`Condition operator ${n}`} className={inputCls} value={c.op} onChange={(e) => setOp(e.target.value)}>
        {spec.ops.map((o) => <option key={o} value={o}>{OPS[o]}</option>)}
      </select>
      <div>{value}</div>
      <Button type="button" variant="secondary" onClick={onRemove} aria-label={`Remove condition ${n}`}>Remove</Button>
    </div>
  );
}

function ActionRow({
  a, i, opts, endpoints, onChange, onRemove,
}: {
  a: RuleAction; i: number; opts: Record<string, Opt[]>; endpoints: Opt[];
  onChange: (a: RuleAction) => void; onRemove: () => void;
}) {
  const n = i + 1;
  const pick = (key: string, label: string, options: Opt[]) => (
    <select aria-label={`${label} ${n}`} className={inputCls} value={a[key] == null ? "" : String(a[key])} onChange={(e) => onChange({ ...a, [key]: e.target.value === "" ? undefined : Number(e.target.value) })}>
      <option value="">Choose…</option>
      {options.map(([k, text]) => <option key={k} value={k}>{text}</option>)}
    </select>
  );
  return (
    <div className="grid items-end gap-2 sm:grid-cols-[1fr_3fr_auto]">
      <select aria-label={`Action type ${n}`} className={inputCls} value={a.type} onChange={(e) => onChange({ type: e.target.value })}>
        {ACTION_TYPES.map(([k, text]) => <option key={k} value={k}>{text}</option>)}
      </select>
      <div className="flex gap-2">
        {a.type === "assign" && pick("user_id", "Action person", opts.user)}
        {a.type === "notify" && pick("user_id", "Action person", opts.user)}
        {a.type === "set_queue" && pick("queue_id", "Action queue", opts.queue)}
        {a.type === "set_priority" && pick("priority_id", "Action priority", opts.priority)}
        {a.type === "webhook" && pick("endpoint_id", "Action webhook", endpoints)}
        {a.type === "create_ticket" && (
          <>
            <input aria-label={`Action subject ${n}`} className={inputCls} maxLength={200} placeholder="Subject of the new ticket" value={String(a.subject ?? "")} onChange={(e) => onChange({ ...a, subject: e.target.value })} />
            {pick("queue_id", "Action queue", opts.queue)}
            {pick("priority_id", "Action priority", opts.priority)}
          </>
        )}
        {a.type === "escalate" && <span className="py-1.5 text-sm text-slate-500">Moves to the next more urgent priority.</span>}
      </div>
      <Button type="button" variant="secondary" onClick={onRemove} aria-label={`Remove action ${n}`}>Remove</Button>
    </div>
  );
}

const cleanAction = (a: RuleAction): RuleAction =>
  Object.fromEntries(Object.entries(a).filter(([, v]) => v !== undefined && v !== "")) as RuleAction;
const actionReady = (a: RuleAction) => {
  if (a.type === "assign" || a.type === "notify") return typeof a.user_id === "number";
  if (a.type === "set_queue") return typeof a.queue_id === "number";
  if (a.type === "set_priority") return typeof a.priority_id === "number";
  if (a.type === "webhook") return typeof a.endpoint_id === "number";
  if (a.type === "create_ticket") return String(a.subject ?? "").trim().length > 0;
  return a.type === "escalate";
};
const conditionReady = (c: RuleCondition) =>
  valueless(c.op) || (multi(c.op) ? Array.isArray(c.value) && c.value.length > 0 : c.value !== "" && c.value != null);
const toBody = (d: Draft): RuleBody => ({
  name: d.name.trim(),
  trigger: d.trigger,
  enabled: d.enabled,
  position: d.position,
  conditions: d.conditions.map((c) => (valueless(c.op) ? { field: c.field, op: c.op } : c)),
  actions: d.actions.map(cleanAction),
});

function shown(v: unknown) {
  if (v === null || v === undefined || v === "") return "—";
  return Array.isArray(v) ? v.join(", ") : String(v);
}

function TestResult({ r }: { r: RuleTestResult }) {
  return (
    <div className="mt-2 space-y-2 rounded border border-slate-200 p-3 text-sm">
      <p className={r.matched ? "font-medium text-green-700" : "font-medium text-slate-600"}>
        {r.matched ? "This rule would run on that ticket." : "This rule would not run on that ticket."}
      </p>
      <ul className="space-y-1">
        {r.conditions.map((c, i) => (
          <li key={i}>
            <span className={c.matched ? "text-green-700" : "text-red-700"}>{c.matched ? "Matched" : "Did not match"}</span>{" "}
            {FIELDS[c.field ?? ""]?.label ?? c.field} {OPS[c.op ?? ""] ?? c.op} {shown(c.value)} (ticket has {shown(c.actual)})
          </li>
        ))}
        {r.conditions.length === 0 && <li className="text-slate-500">No conditions: it matches every ticket.</li>}
      </ul>
      {r.actions.length > 0 && (
        <div>
          <p className="font-medium">Would do</p>
          <ul className="list-disc pl-5">
            {r.actions.map((a, i) => <li key={i}>{a.detail}{a.status === "would_skip" ? " (skipped)" : ""}</li>)}
          </ul>
        </div>
      )}
    </div>
  );
}

function History({ rule }: { rule: AutomationRule }) {
  const runs = useQuery({ queryKey: ["rule-runs", rule.id], queryFn: () => listRuleRuns(rule.id) });
  return (
    <div className="mt-2 rounded border border-slate-200 p-2">
      <ErrorMsg error={runs.error} />
      <table className="w-full text-left text-sm">
        <thead className="border-b border-slate-200 text-slate-500">
          <tr><th className="p-1">When</th><th>Event</th><th>Ticket</th><th>Result</th><th>Actions</th></tr>
        </thead>
        <tbody>
          {runs.data?.map((r) => (
            <tr key={r.id} className="border-b border-slate-100 align-top">
              <td className="p-1">{fmt(r.created_at)}</td>
              <td>{triggerLabel(r.event_type)}</td>
              <td>{r.ticket_id ?? "—"}</td>
              <td>{r.matched ? "Matched" : "No match"}</td>
              <td>{r.trace.actions.map((a) => `${a.type}: ${a.status}${a.detail ? ` (${a.detail})` : ""}`).join("; ") || "—"}</td>
            </tr>
          ))}
          {runs.data?.length === 0 && <tr><td colSpan={5} className="p-2 text-slate-500">This rule has not run yet.</td></tr>}
        </tbody>
      </table>
    </div>
  );
}

export default function Automation() {
  const qc = useQueryClient();
  const list = useQuery({ queryKey: ["automation-rules"], queryFn: listRules });
  const { byKind, endpoints } = useOptions();
  const [draft, setDraft] = useState<Draft>(blank());
  const [history, setHistory] = useState<number | null>(null);
  const [ticketNo, setTicketNo] = useState("");
  const [result, setResult] = useState<RuleTestResult | null>(null);
  const refresh = () => qc.invalidateQueries({ queryKey: ["automation-rules"] });
  const set = (patch: Partial<Draft>) => setDraft((d) => ({ ...d, ...patch }));
  const [base, setBase] = useState(() => JSON.stringify(blank()));
  const dirty = JSON.stringify(draft) !== base;
  const formRef = useRef<HTMLDivElement>(null);
  const nameRef = useRef<HTMLInputElement>(null);

  const resetDraft = () => {
    setBase(JSON.stringify(blank()));
    setDraft(blank());
    setResult(null);
  };

  const save = useMutation({
    mutationFn: () => (draft.id == null ? createRule(toBody(draft)) : updateRule(draft.id, toBody(draft))),
    onSuccess: () => {
      resetDraft();
      refresh();
    },
  });
  const toggle = useMutation({
    mutationFn: (r: AutomationRule) => updateRule(r.id, { enabled: !r.enabled }),
    onSuccess: refresh,
  });
  const archive = useMutation({
    mutationFn: (id: number) => archiveRule(id),
    onSuccess: () => {
      resetDraft();
      refresh();
    },
  });
  const test = useMutation({
    mutationFn: () => testRule({ rule: toBody(draft), ticket_id: Number(ticketNo) }),
    onSuccess: setResult,
  });
  const edit = (r: AutomationRule) => {
    if (dirty && !window.confirm("Replace the unsaved changes in the form?")) return;
    setResult(null);
    const next: Draft = { id: r.id, name: r.name, trigger: r.trigger, enabled: r.enabled, position: r.position, conditions: r.conditions, actions: r.actions };
    setBase(JSON.stringify(next));
    setDraft(next);
    setTimeout(() => {
      formRef.current?.scrollIntoView?.({ behavior: "smooth", block: "start" });
      nameRef.current?.focus();
    }, 0);
  };
  const onTrigger = (trigger: string) =>
    set({ trigger, conditions: trigger.startsWith("rmm_alert.") ? draft.conditions : draft.conditions.filter((c) => c.field !== "alert_severity") });
  const onArchive = () => {
    if (draft.id != null && window.confirm(`Archive the rule "${draft.name}"? It stops running and is hidden from this list.`)) archive.mutate(draft.id);
  };
  const badCondition = draft.conditions.findIndex((c) => !conditionReady(c));
  const badAction = draft.actions.findIndex((a) => !actionReady(a));
  const unmet =
    draft.name.trim().length === 0 ? "Enter a name"
    : draft.actions.length === 0 ? "Add at least one action"
    : badCondition >= 0 ? `Choose a value for condition ${badCondition + 1}`
    : badAction >= 0 ? `Finish action ${badAction + 1}`
    : null;
  const ready = unmet === null;

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold tracking-tight">Automation</h1>
      <p className="text-sm text-slate-600">
        Rules do routine work for you: when something happens and every condition is true, they assign, re-queue, escalate, notify, call a webhook
        or open a related ticket. Rules never trigger other rules, and a rule that fires more than 200 times in an hour is switched off.
      </p>
      <Card title="Rules">
        <ErrorMsg error={list.error ?? toggle.error} />
        <ul className="space-y-3">
          {list.data?.map((r) => (
            <li key={r.id} aria-current={draft.id === r.id ? "true" : undefined} className={`rounded border p-3 ${draft.id === r.id ? "border-blue-500 bg-blue-50" : "border-slate-200"}`}>
              <div className="flex flex-wrap items-center gap-3">
                <strong>{r.name}</strong>
                <span className="text-sm text-slate-500">{triggerLabel(r.trigger)}</span>
                <span className="text-sm">Fired {r.fire_count} {r.fire_count === 1 ? "time" : "times"}</span>
                <span className="text-xs text-slate-500">Last fired: {fmt(r.last_fired_at)}</span>
                <label className="ml-auto flex items-center gap-1 text-sm">
                  <input type="checkbox" checked={r.enabled} disabled={toggle.isPending} onChange={() => toggle.mutate(r)} aria-label={`Enabled ${r.name}`} />
                  Enabled
                </label>
              </div>
              {r.disabled_reason && (
                <p role="alert" className="mt-1 rounded bg-amber-50 px-3 py-1 text-sm text-amber-800">Switched off: {r.disabled_reason}</p>
              )}
              <div className="mt-2 flex gap-2">
                <Button type="button" variant="secondary" onClick={() => edit(r)} aria-label={`Edit ${r.name}`}>Edit</Button>
                <Button type="button" variant="secondary" onClick={() => setHistory(history === r.id ? null : r.id)} aria-label={`History for ${r.name}`}>
                  {history === r.id ? "Hide history" : "History"}
                </Button>
              </div>
              {history === r.id && <History rule={r} />}
            </li>
          ))}
          {list.data?.length === 0 && <li className="text-sm text-slate-500">No rules yet.</li>}
        </ul>
      </Card>
      <div ref={formRef}>
      <Card title={draft.id == null ? "New rule" : `Edit rule: ${draft.name}`}>
        <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="Name"><input ref={nameRef} className={inputCls} required maxLength={100} value={draft.name} onChange={(e) => set({ name: e.target.value })} /></Field>
            <Field label="When">
              <select className={inputCls} value={draft.trigger} onChange={(e) => onTrigger(e.target.value)}>
                {TRIGGERS.map(([k, text]) => <option key={k} value={k}>{text}</option>)}
              </select>
            </Field>
            <Field label="Order (lower runs first)">
              <input className={inputCls} type="number" min={0} max={10000} value={draft.position} onChange={(e) => set({ position: Number(e.target.value) })} />
            </Field>
          </div>
          <fieldset className="space-y-2">
            <legend className="mb-1 text-sm font-medium">Only if all of these are true</legend>
            {draft.conditions.map((c, i) => (
              <ConditionRow
                key={i} c={c} i={i} trigger={draft.trigger} opts={byKind}
                onChange={(nc) => set({ conditions: draft.conditions.map((x, j) => (j === i ? nc : x)) })}
                onRemove={() => set({ conditions: draft.conditions.filter((_, j) => j !== i) })}
              />
            ))}
            {draft.conditions.length === 0 && <p className="text-sm text-slate-500">No conditions: the rule applies every time.</p>}
            <Button type="button" variant="secondary" onClick={() => set({ conditions: [...draft.conditions, { field: "queue_id", op: "eq", value: "" }] })}>Add condition</Button>
          </fieldset>
          <fieldset className="space-y-2">
            <legend className="mb-1 text-sm font-medium">Then do</legend>
            {draft.actions.map((a, i) => (
              <ActionRow
                key={i} a={a} i={i} opts={byKind} endpoints={endpoints}
                onChange={(na) => set({ actions: draft.actions.map((x, j) => (j === i ? na : x)) })}
                onRemove={() => set({ actions: draft.actions.filter((_, j) => j !== i) })}
              />
            ))}
            <Button type="button" variant="secondary" onClick={() => set({ actions: [...draft.actions, { type: "escalate" }] })}>Add action</Button>
          </fieldset>
          <div className="flex flex-wrap items-end gap-2">
            <label className="flex items-center gap-1 text-sm">
              <input type="checkbox" checked={draft.enabled} onChange={(e) => set({ enabled: e.target.checked })} />
              Enabled
            </label>
            <div className="ml-auto flex items-end gap-2">
              <Field label="Test against ticket #">
                <input className={`${inputCls} w-32`} inputMode="numeric" value={ticketNo} onChange={(e) => setTicketNo(e.target.value)} />
              </Field>
              <Button type="button" variant="secondary" disabled={!ready || !/^\d+$/.test(ticketNo) || test.isPending} onClick={() => test.mutate()}>Test rule</Button>
            </div>
          </div>
          <ErrorMsg error={test.error} />
          {result && <TestResult r={result} />}
          <ErrorMsg error={save.error ?? archive.error} />
          <div className="flex gap-2">
            <Button type="submit" disabled={!ready || save.isPending}>Save rule</Button>
            {unmet && <span className="self-center text-sm text-slate-600">{unmet} to save.</span>}
            {draft.id != null && <Button type="button" variant="danger" onClick={onArchive}>Archive rule</Button>}
            {draft.id != null && <Button type="button" variant="secondary" onClick={resetDraft}>Cancel</Button>}
          </div>
        </form>
      </Card>
      </div>
    </div>
  );
}
