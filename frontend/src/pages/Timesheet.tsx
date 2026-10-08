import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { Lookup, Timesheet as Sheet, api } from "../api";
import { Button, Card, ErrorMsg, Field, inputCls } from "../ui";

const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
export function mondayOf(d: Date) {
  const x = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  x.setDate(x.getDate() - ((x.getDay() + 6) % 7));
  return x;
}
const hours = (m: number) => (m / 60).toFixed(2);
const DAY = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export default function Timesheet() {
  const qc = useQueryClient();
  const [week, setWeek] = useState(() => mondayOf(new Date()));
  const start = iso(week);
  const q = useQuery({ queryKey: ["timesheet", start], queryFn: () => api<Sheet>(`/timesheet?week_start=${start}`) });
  const cats = useQuery({ queryKey: ["lookup", "time-categories"], queryFn: () => api<Lookup[]>("/time-categories") });
  const shift = (days: number) => { const d = new Date(week); d.setDate(d.getDate() + days); setWeek(d); };
  const [f, setF] = useState({ category_id: "", work_date: iso(new Date()), minutes: "", note: "" });
  const refresh = () => qc.invalidateQueries({ queryKey: ["timesheet"] });
  const add = useMutation({
    mutationFn: () => api("/internal-time", { method: "POST", json: { category_id: Number(f.category_id), work_date: f.work_date, minutes: Number(f.minutes), note: f.note || null } }),
    onSuccess: () => { setF({ ...f, minutes: "", note: "" }); refresh(); },
  });
  const voidIt = useMutation({ mutationFn: (id: number) => api(`/internal-time/${id}/void`, { method: "POST" }), onSuccess: refresh });
  const voidTicket = useMutation({ mutationFn: (id: number) => api(`/time-entries/${id}/void`, { method: "POST" }), onSuccess: refresh });
  const s = q.data;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-bold tracking-tight">My timesheet</h1>
        <span className="ml-auto flex items-center gap-2">
          <Button variant="secondary" onClick={() => shift(-7)}>← Previous</Button>
          <span className="text-sm">Week of <b>{start}</b></span>
          <Button variant="secondary" onClick={() => shift(7)}>Next →</Button>
          <Button variant="secondary" onClick={() => setWeek(mondayOf(new Date()))}>This week</Button>
        </span>
      </div>
      <ErrorMsg error={q.error ?? voidIt.error ?? voidTicket.error} />
      {s && (
        <>
          <Card title="Hours">
            <table className="w-full text-center text-sm">
              <thead className="text-slate-500"><tr>{s.days.map((d, i) => <th key={d.date}>{DAY[i]} <span className="text-xs">{d.date.slice(5)}</span></th>)}<th>Total</th></tr></thead>
              <tbody>
                <tr>{s.days.map((d) => <td key={d.date} className="tabular-nums">{d.minutes ? hours(d.minutes) : "—"}</td>)}<td className="font-bold tabular-nums">{hours(s.total_minutes)}</td></tr>
              </tbody>
            </table>
            <p className="mt-2 text-sm text-slate-600">
              Billable ticket time: <b>{hours(s.billable_minutes)} h</b> · Internal: <b>{hours(s.internal_minutes)} h</b> · Total logged: <b>{hours(s.total_minutes)} h</b>
            </p>
          </Card>
          <Card title="Entries">
            <table className="w-full text-left text-sm">
              <thead className="text-slate-500"><tr><th>Date</th><th>What</th><th>Type</th><th>Minutes</th><th>Note</th><th /></tr></thead>
              <tbody>
                {s.entries.map((e) => (
                  <tr key={`${e.kind}-${e.id}`} className="border-t border-slate-100">
                    <td>{e.work_date}</td>
                    <td>{e.ticket_id ? <Link className="text-blue-700 hover:underline" to={`/tickets/${e.ticket_id}`}>{e.label}</Link> : e.label}</td>
                    <td>{e.detail}{e.kind === "ticket" && !e.billable && " (non-billable)"}{e.invoiced && " · invoiced"}</td>
                    <td>{e.minutes_actual}</td>
                    <td>{e.note}</td>
                    <td>{!e.invoiced && <button className="text-red-700 hover:underline" onClick={() => (e.kind === "ticket" ? voidTicket : voidIt).mutate(e.id)}>Void</button>}</td>
                  </tr>
                ))}
                {s.entries.length === 0 && <tr><td colSpan={6} className="text-slate-500">Nothing logged this week.</td></tr>}
              </tbody>
            </table>
          </Card>
        </>
      )}
      <Card title="Log internal time">
        <p className="mb-2 text-sm text-slate-600">For work that is not for a client: administration, training, meetings, paid time off. Time on a ticket is logged from the ticket.</p>
        <form className="flex flex-wrap items-end gap-2" onSubmit={(e) => { e.preventDefault(); add.mutate(); }}>
          <Field label="Category">
            <select className={inputCls} required value={f.category_id} onChange={(e) => setF({ ...f, category_id: e.target.value })}>
              <option value="">Select…</option>
              {cats.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </Field>
          <Field label="Date"><input className={inputCls} type="date" required value={f.work_date} onChange={(e) => setF({ ...f, work_date: e.target.value })} /></Field>
          <div className="w-24"><Field label="Minutes"><input className={inputCls} type="number" min={1} max={1440} required value={f.minutes} onChange={(e) => setF({ ...f, minutes: e.target.value })} /></Field></div>
          <div className="w-64"><Field label="Note"><input className={inputCls} value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} /></Field></div>
          <Button type="submit" disabled={add.isPending}>Add</Button>
        </form>
        <ErrorMsg error={add.error} />
      </Card>
      <InternalTimer cats={cats.data ?? []} />
    </div>
  );
}

function InternalTimer({ cats }: { cats: Lookup[] }) {
  const qc = useQueryClient();
  const [cat, setCat] = useState("");
  const start = useMutation({
    mutationFn: () => api("/timer/start", { method: "POST", json: { category_id: Number(cat) } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["timer"] }),
  });
  return (
    <Card title="Start an internal timer">
      <div className="flex flex-wrap items-end gap-2">
        <Field label="Category">
          <select className={inputCls} value={cat} onChange={(e) => setCat(e.target.value)}>
            <option value="">Select…</option>
            {cats.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </Field>
        <Button disabled={!cat || start.isPending} onClick={() => start.mutate()}>Start timer</Button>
      </div>
      <ErrorMsg error={start.error} />
    </Card>
  );
}
