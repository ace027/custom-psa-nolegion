import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { BillingMode, PROJECT_STATUS_LABEL, Project, ProjectInput, ProjectPhase, ProjectStatus, ProjectTask, projectsApi } from "../api";
import { can, useMe } from "../auth";
import { useLookups } from "../lookups";
import { money, parseMoney } from "../money";
import { Button, Card, ErrorMsg, Field, StatTile, inputCls } from "../ui";
import ProjectBoard from "./ProjectBoard";
import { MODE_LABEL, hours } from "./Projects";
import { clientRoute } from "../clientScope";

type Tab = "tasks" | "board" | "budget";
const TABS: { key: Tab; label: string }[] = [
  { key: "tasks", label: "Tasks" },
  { key: "board", label: "Board" },
  { key: "budget", label: "Budget" },
];
// Mirrors the server rules; draft becomes active only through Approve.
const NEXT: Record<ProjectStatus, { to: ProjectStatus; label: string }[]> = {
  draft: [{ to: "cancelled", label: "Cancel project" }],
  active: [
    { to: "on_hold", label: "Put on hold" },
    { to: "completed", label: "Complete" },
    { to: "cancelled", label: "Cancel project" },
  ],
  on_hold: [{ to: "active", label: "Resume" }],
  completed: [],
  cancelled: [],
};

export default function ProjectDetail() {
  const id = Number(useParams().id);
  const { data: me } = useMe();
  const canWrite = can(me, "project:write");
  const canBill = can(me, "billing:write");
  const qc = useQueryClient();
  const [tab, setTab] = useState<Tab>("tasks");
  const q = useQuery({ queryKey: ["project", id], queryFn: () => projectsApi.get(id) });
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["project", id] });
    qc.invalidateQueries({ queryKey: ["project-budget", id] });
    qc.invalidateQueries({ queryKey: ["projects"] });
  };
  const status = useMutation({ mutationFn: (s: ProjectStatus) => projectsApi.setStatus(id, s), onSuccess: refresh });
  const approve = useMutation({ mutationFn: () => projectsApi.approve(id), onSuccess: refresh });
  const bill = useMutation({ mutationFn: () => projectsApi.billFixedFee(id), onSuccess: refresh });

  const p = q.data;
  if (q.isLoading) return <p>Loading…</p>;
  if (!p) return <ErrorMsg error={q.error ?? "Not found"} />;
  const closed = p.status === "completed" || p.status === "cancelled";
  const writable = canWrite && !closed;
  return (
    <div className="space-y-4">
      <div>
        <p className="text-sm"><Link className="text-blue-700 hover:underline" to="/projects">Projects</Link> / <Link className="text-blue-700 hover:underline" to={clientRoute(p.organization_id)}>{p.organization_name}</Link></p>
        <h1 className="text-2xl font-bold tracking-tight">{p.name}</h1>
        <p className="text-sm text-slate-600">
          {PROJECT_STATUS_LABEL[p.status]}
          {p.billing_mode && ` · ${MODE_LABEL[p.billing_mode]}`}
          {` · ${p.done_count}/${p.task_count} tasks done`}
          {p.start_date && ` · starts ${p.start_date}`}
          {p.due_date && ` · due ${p.due_date}`}
        </p>
        {p.description && <p className="mt-1 whitespace-pre-wrap text-sm">{p.description}</p>}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {writable && NEXT[p.status].map((n) => (
          <Button key={n.to} aria-label={n.to === "cancelled" ? `Cancel project ${p.name}` : undefined} variant={n.to === "cancelled" ? "danger" : "secondary"} disabled={status.isPending} onClick={() => { if (n.to !== "cancelled" || window.confirm(`Cancel project "${p.name}"? A cancelled project cannot be reopened.`)) status.mutate(n.to); }}>{n.label}</Button>
        ))}
        {canBill && p.status === "draft" && <Button disabled={approve.isPending} onClick={() => approve.mutate()}>Approve</Button>}
        {p.billing_mode === "fixed_fee" && p.approved_at && (
          p.fixed_fee_billed ? (
            <span className="rounded-full bg-green-100 px-3 py-1 text-sm font-semibold text-green-800">Fixed fee billed</span>
          ) : (
            canBill && !closed && <Button disabled={bill.isPending} onClick={() => bill.mutate()}>Bill fixed fee now</Button>
          )
        )}
      </div>
      <ErrorMsg error={status.error ?? approve.error ?? bill.error} />
      <div role="tablist" aria-label="Project sections" className="flex gap-1 border-b border-slate-200">
        {TABS.map((t, i) => (
          <button
            key={t.key}
            id={`project-tab-${t.key}`}
            type="button"
            role="tab"
            aria-selected={tab === t.key}
            aria-controls="project-tabpanel"
            tabIndex={tab === t.key ? 0 : -1}
            className={`px-3 py-2 text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 ${tab === t.key ? "border-b-2 border-blue-600 font-semibold text-blue-700" : "text-slate-700"}`}
            onClick={() => setTab(t.key)}
            onKeyDown={(e) => {
              let next = -1;
              if (e.key === "ArrowRight") next = (i + 1) % TABS.length;
              else if (e.key === "ArrowLeft") next = (i - 1 + TABS.length) % TABS.length;
              else if (e.key === "Home") next = 0;
              else if (e.key === "End") next = TABS.length - 1;
              if (next < 0) return;
              e.preventDefault();
              setTab(TABS[next].key);
              document.getElementById(`project-tab-${TABS[next].key}`)?.focus();
            }}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div role="tabpanel" id="project-tabpanel" aria-labelledby={`project-tab-${tab}`}>
        {tab === "tasks" && <TasksTab project={p} canWrite={writable} onDone={refresh} />}
        {tab === "board" && <ProjectBoard project={p} canWrite={writable} />}
        {tab === "budget" && <BudgetTab project={p} canBill={canBill} onDone={refresh} />}
      </div>
    </div>
  );
}

// ---- tasks ----
interface TaskValues {
  title: string;
  phase: string;
  assignee: string;
  estimate: string;
  start: string;
  due: string;
  deps: number[];
}
const blankTask: TaskValues = { title: "", phase: "", assignee: "", estimate: "", start: "", due: "", deps: [] };

function TasksTab({ project: p, canWrite, onDone }: { project: Project; canWrite: boolean; onDone: () => void }) {
  const [adding, setAdding] = useState(false);
  const [addingPhase, setAddingPhase] = useState(false);
  const empty = p.phases.length === 0 && p.tasks.length === 0;
  const groups: { phase: ProjectPhase | null; tasks: ProjectTask[] }[] = [
    ...p.phases.map((ph) => ({ phase: ph, tasks: p.tasks.filter((t) => t.phase_id === ph.id) })),
    { phase: null, tasks: p.tasks.filter((t) => t.phase_id === null || !p.phases.some((ph) => ph.id === t.phase_id)) },
  ].filter((g) => g.phase || g.tasks.length > 0);
  return (
    <div className="space-y-4">
      {canWrite && !empty && (
        <div className="flex gap-2">
          <Button variant="secondary" onClick={() => setAdding(!adding)}>Add task</Button>
          <Button variant="secondary" onClick={() => setAddingPhase(!addingPhase)}>Add phase</Button>
        </div>
      )}
      {addingPhase && canWrite && <PhaseForm project={p} onDone={() => { setAddingPhase(false); onDone(); }} />}
      {adding && canWrite && <Card title="New task"><TaskForm project={p} onDone={() => { setAdding(false); onDone(); }} /></Card>}
      {empty && !adding && (
        <Card title="Tasks">
          <p className="mb-3 text-sm text-slate-500">This project has no phases or tasks yet.</p>
          {canWrite && (
            <div className="flex gap-2">
              <Button onClick={() => setAdding(true)}>Add task</Button>
              <Button variant="secondary" onClick={() => setAddingPhase(true)}>Add phase</Button>
            </div>
          )}
        </Card>
      )}
      {groups.map((g) => (
        <Card key={g.phase?.id ?? "none"} title={g.phase ? g.phase.name : "No phase"} actions={g.phase ? <PhaseActions project={p} phase={g.phase} canWrite={canWrite} onDone={onDone} /> : undefined}>
          {g.tasks.length === 0 ? (
            <p className="text-sm text-slate-500">No tasks in this phase.</p>
          ) : (
            <ul className="divide-y divide-slate-100 text-sm">
              {g.tasks.map((t) => <TaskRow key={t.id} project={p} task={t} canWrite={canWrite} onDone={onDone} />)}
            </ul>
          )}
        </Card>
      ))}
    </div>
  );
}

function PhaseForm({ project, onDone }: { project: Project; onDone: () => void }) {
  const [name, setName] = useState("");
  const [due, setDue] = useState("");
  const add = useMutation({ mutationFn: () => projectsApi.addPhase(project.id, { name, due_date: due || null }), onSuccess: onDone });
  return (
    <Card title="New phase">
      <form className="flex flex-wrap items-end gap-2" onSubmit={(e) => { e.preventDefault(); add.mutate(); }}>
        <Field label="Phase name"><input className={inputCls} required value={name} onChange={(e) => setName(e.target.value)} /></Field>
        <Field label="Phase due"><input className={inputCls} type="date" value={due} onChange={(e) => setDue(e.target.value)} /></Field>
        <Button type="submit" disabled={add.isPending}>Save phase</Button>
      </form>
      <ErrorMsg error={add.error} />
    </Card>
  );
}

function PhaseActions({ project, phase, canWrite, onDone }: { project: Project; phase: ProjectPhase; canWrite: boolean; onDone: () => void }) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(phase.name);
  const [due, setDue] = useState(phase.due_date ?? "");
  const save = useMutation({ mutationFn: () => projectsApi.updatePhase(project.id, phase.id, { name, due_date: due || null }), onSuccess: () => { setEditing(false); onDone(); } });
  const toggle = useMutation({ mutationFn: () => projectsApi.updatePhase(project.id, phase.id, { completed: !phase.completed_at }), onSuccess: onDone });
  const del = useMutation({ mutationFn: () => projectsApi.deletePhase(project.id, phase.id), onSuccess: onDone });
  return (
    <div className="flex flex-wrap items-center gap-2 text-sm">
      <span className="text-slate-500">{phase.due_date ? `due ${phase.due_date}` : ""}{phase.completed_at ? " · complete" : ""}</span>
      {canWrite && (
        <>
          <Button variant="secondary" aria-label={`Edit phase ${phase.name}`} onClick={() => setEditing(!editing)}>Edit phase</Button>
          <Button variant="secondary" aria-label={`${phase.completed_at ? "Reopen" : "Complete"} phase ${phase.name}`} onClick={() => toggle.mutate()}>{phase.completed_at ? "Reopen phase" : "Complete phase"}</Button>
          {phase.task_count === 0 && <Button variant="danger" aria-label={`Delete phase ${phase.name}`} onClick={() => { if (window.confirm(`Delete phase "${phase.name}"?`)) del.mutate(); }}>Delete phase</Button>}
        </>
      )}
      {editing && (
        <form className="flex items-end gap-2" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
          <Field label="Name"><input className={inputCls} required value={name} onChange={(e) => setName(e.target.value)} /></Field>
          <Field label="Due"><input className={inputCls} type="date" value={due} onChange={(e) => setDue(e.target.value)} /></Field>
          <Button type="submit">Save</Button>
        </form>
      )}
      <ErrorMsg error={save.error ?? toggle.error ?? del.error} />
    </div>
  );
}

function TaskRow({ project, task: t, canWrite, onDone }: { project: Project; task: ProjectTask; canWrite: boolean; onDone: () => void }) {
  const [editing, setEditing] = useState(false);
  const byId = new Map(project.tasks.map((x) => [x.id, x]));
  return (
    <li className="py-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span>
          <Link className="font-medium text-blue-700 hover:underline" to={`/tickets/${t.ticket_id}`}>#{t.ticket_number}</Link> {t.title}{" "}
          <span className="text-xs text-slate-500">({t.status_name})</span>
          {t.blocked && <span className="ml-2 rounded-full bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-800">Blocked</span>}
        </span>
        <span className="flex items-center gap-3 text-xs text-slate-600">
          <span>{t.assignee_name ?? "Unassigned"}</span>
          <span>{hours(t.actual_minutes)} / {hours(t.estimate_minutes)}</span>
          {t.due_date && <span>Due {t.due_date}</span>}
          {canWrite && <Button variant="secondary" onClick={() => setEditing(!editing)}>{editing ? "Close" : `Edit #${t.ticket_number}`}</Button>}
        </span>
      </div>
      {t.depends_on.length > 0 && (
        <p className="text-xs text-slate-500">Depends on {t.depends_on.map((d) => `#${byId.get(d)?.ticket_number ?? d}`).join(", ")}</p>
      )}
      {editing && canWrite && <div className="mt-2"><TaskForm project={project} task={t} onDone={() => { setEditing(false); onDone(); }} /></div>}
    </li>
  );
}

function TaskForm({ project, task, onDone }: { project: Project; task?: ProjectTask; onDone: () => void }) {
  const lk = useLookups();
  const [v, setV] = useState<TaskValues>(
    task
      ? {
          title: task.title,
          phase: task.phase_id ? String(task.phase_id) : "",
          assignee: task.assignee_id ? String(task.assignee_id) : "",
          estimate: task.estimate_minutes ? String(task.estimate_minutes / 60) : "",
          start: task.start_date ?? "",
          due: task.due_date ?? "",
          deps: task.depends_on,
        }
      : blankTask,
  );
  const others = project.tasks.filter((x) => x.id !== task?.id);
  const save = useMutation({
    mutationFn: async () => {
      const est = v.estimate.trim() === "" ? 0 : Math.round(Number(v.estimate) * 60);
      if (!Number.isFinite(est) || est < 0) throw new Error("Estimate must be a number of hours");
      const body = {
        title: v.title,
        phase_id: v.phase ? Number(v.phase) : null,
        assignee_id: v.assignee ? Number(v.assignee) : null,
        estimate_minutes: est,
        start_date: v.start || null,
        due_date: v.due || null,
      };
      const saved = task ? await projectsApi.updateTask(project.id, task.id, body) : await projectsApi.addTask(project.id, body);
      const before = task?.depends_on ?? [];
      for (const d of v.deps.filter((d) => !before.includes(d))) await projectsApi.addDependency(project.id, saved.id, d);
      for (const d of before.filter((d) => !v.deps.includes(d))) await projectsApi.removeDependency(project.id, saved.id, d);
    },
    onSuccess: onDone,
  });
  const toggleDep = (id: number) => setV({ ...v, deps: v.deps.includes(id) ? v.deps.filter((d) => d !== id) : [...v.deps, id] });
  return (
    <form className="grid gap-3 sm:grid-cols-3" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
      <Field label="Task title"><input className={inputCls} required value={v.title} onChange={(e) => setV({ ...v, title: e.target.value })} /></Field>
      <Field label="Phase">
        <select className={inputCls} value={v.phase} onChange={(e) => setV({ ...v, phase: e.target.value })}>
          <option value="">No phase</option>
          {project.phases.map((ph) => <option key={ph.id} value={ph.id}>{ph.name}</option>)}
        </select>
      </Field>
      <Field label="Assignee">
        <select className={inputCls} value={v.assignee} onChange={(e) => setV({ ...v, assignee: e.target.value })}>
          <option value="">Unassigned</option>
          {lk.techs.map((u) => <option key={u.id} value={u.id}>{u.display_name}</option>)}
        </select>
      </Field>
      <Field label="Estimate (hours)"><input className={inputCls} inputMode="decimal" value={v.estimate} onChange={(e) => setV({ ...v, estimate: e.target.value })} /></Field>
      <Field label="Start"><input className={inputCls} type="date" value={v.start} onChange={(e) => setV({ ...v, start: e.target.value })} /></Field>
      <Field label="Due"><input className={inputCls} type="date" value={v.due} onChange={(e) => setV({ ...v, due: e.target.value })} /></Field>
      {others.length > 0 && (
        <fieldset className="col-span-full text-sm">
          <legend className="mb-1 font-medium text-slate-700">Depends on</legend>
          <div className="grid max-h-48 grid-cols-1 gap-y-1 overflow-y-auto rounded border border-slate-200 p-2 sm:grid-cols-2">
            {others.map((o) => (
              <label key={o.id} className="flex items-center gap-1">
                <input type="checkbox" checked={v.deps.includes(o.id)} onChange={() => toggleDep(o.id)} />#{o.ticket_number} {o.title}
              </label>
            ))}
          </div>
        </fieldset>
      )}
      <div className="col-span-full space-y-2">
        <ErrorMsg error={save.error} />
        <Button type="submit" disabled={save.isPending}>{task ? "Save task" : "Add task to project"}</Button>
      </div>
    </form>
  );
}

// ---- budget ----
function BudgetTab({ project: p, canBill, onDone }: { project: Project; canBill: boolean; onDone: () => void }) {
  const b = p.budget;
  const cap = p.billing_mode === "fixed_fee" ? p.fixed_fee_cents : p.budget_cents;
  return (
    <div className="space-y-4">
      {b.over_budget && (
        <div role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800">
          Over budget: work at rates costs {money(b.cost_at_rates_cents)}{cap != null && ` against ${money(cap)}`}. Further time is billed at $0.
        </div>
      )}
      <Card title="Budget vs actual">
        <div className="grid gap-3 sm:grid-cols-3">
          <StatTile value={hours(b.estimate_minutes)} label="Estimated" />
          <StatTile value={hours(b.actual_minutes)} label="Actual" />
          <StatTile value={hours(b.billable_minutes)} label="Billable" />
          <StatTile value={money(b.cost_at_rates_cents)} label="Cost at rates" />
          <StatTile value={money(b.billed_cents)} label="Billed" />
          <StatTile
            value={b.remaining_cents === null ? "—" : `${money(b.remaining_cents)}${b.over_budget ? " (over)" : ""}`}
            label={b.remaining_cents === null ? "Remaining (fixed fee)" : "Remaining"}
            tone={b.over_budget ? "text-red-700" : ""}
          />
        </div>
        <p className="mt-3 text-sm text-slate-600">
          {p.billing_mode ? MODE_LABEL[p.billing_mode] : "No billing mode set"}
          {cap != null && ` · ${p.billing_mode === "fixed_fee" ? "fee" : "budget"} ${money(cap)}`}
          {p.billing_mode && ` · ${p.taxable ? "taxable" : "not taxable"}`}
        </p>
      </Card>
      {canBill && p.status === "draft" && <BillingForm project={p} onDone={onDone} />}
    </div>
  );
}

function BillingForm({ project: p, onDone }: { project: Project; onDone: () => void }) {
  const cents = (c: number | null) => (c == null ? "" : (c / 100).toFixed(2));
  const [mode, setMode] = useState<string>(p.billing_mode ?? "");
  const [fee, setFee] = useState(cents(p.fixed_fee_cents));
  const [budget, setBudget] = useState(cents(p.budget_cents));
  const [taxable, setTaxable] = useState(p.taxable);
  const save = useMutation({
    mutationFn: () => {
      const json: ProjectInput = { billing_mode: (mode || null) as BillingMode | null, taxable };
      if (mode === "fixed_fee") {
        const c = parseMoney(fee);
        if (c === null || c <= 0) throw new Error("Enter the fixed fee, e.g. 2500.00");
        json.fixed_fee_cents = c;
      }
      if (mode === "tm" && budget.trim()) {
        const c = parseMoney(budget);
        if (c === null || c <= 0) throw new Error("Enter a valid budget, e.g. 1000.00");
        json.budget_cents = c;
      }
      return projectsApi.update(p.id, json);
    },
    onSuccess: onDone,
  });
  return (
    <Card title="Billing terms (set before approval)">
      <form className="grid gap-3 sm:grid-cols-4" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
        <Field label="Billing mode">
          <select className={inputCls} value={mode} onChange={(e) => setMode(e.target.value)}>
            <option value="">Not set</option>
            <option value="fixed_fee">Fixed fee</option>
            <option value="tm">Time & materials</option>
          </select>
        </Field>
        {mode === "fixed_fee" && <Field label="Fixed fee ($)"><input className={inputCls} inputMode="decimal" value={fee} onChange={(e) => setFee(e.target.value)} /></Field>}
        {mode === "tm" && <Field label="Budget ($)"><input className={inputCls} inputMode="decimal" value={budget} onChange={(e) => setBudget(e.target.value)} /></Field>}
        <label className="flex items-end gap-1 text-sm"><input type="checkbox" checked={taxable} onChange={(e) => setTaxable(e.target.checked)} />Taxable</label>
        <div className="col-span-full space-y-2">
          <ErrorMsg error={save.error} />
          <Button type="submit" disabled={save.isPending}>Save billing terms</Button>
        </div>
      </form>
    </Card>
  );
}
