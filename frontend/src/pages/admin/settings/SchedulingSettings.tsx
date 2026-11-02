import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Holiday, api } from "../../../api";
import { Button, Card, ErrorMsg, Field, inputCls } from "../../../ui";

export default function SchedulingSettings() {
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold tracking-tight">Scheduling</h1>
      <HolidaysCard />
    </div>
  );
}

const hhmm = (m: number) => `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;

function HolidaysCard() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["cfg", "holidays"], queryFn: () => api<Holiday[]>("/holidays") });
  const [f, setF] = useState({ on_date: "", name: "", short: false, open: "09:00", close: "12:00" });
  const toMin = (v: string) => Number(v.slice(0, 2)) * 60 + Number(v.slice(3, 5));
  const refresh = () => qc.invalidateQueries({ queryKey: ["cfg", "holidays"] });
  const add = useMutation({
    mutationFn: () =>
      api("/holidays", {
        method: "POST",
        json: { on_date: f.on_date, name: f.name, open_minute: f.short ? toMin(f.open) : null, close_minute: f.short ? toMin(f.close) : null },
      }),
    onSuccess: () => { setF({ ...f, on_date: "", name: "" }); refresh(); },
  });
  const del = useMutation({ mutationFn: (id: number) => api(`/holidays/${id}`, { method: "DELETE" }), onSuccess: refresh });
  return (
    <Card title="Holidays">
      <p className="mb-2 text-sm text-slate-600">SLA clocks do not run on a closed day, and run only the shortened hours on a half day. Only affects business days. Tickets that already have a due date keep it until something recomputes it.</p>
      <ul className="divide-y divide-slate-100 text-sm">
        {q.data?.map((h) => (
          <li key={h.id} className="flex items-center justify-between py-1.5">
            <span>
              <b>{h.on_date}</b> {h.name}
              <span className="ml-2 text-slate-500">{h.open_minute === null || h.close_minute === null ? "closed" : `open ${hhmm(h.open_minute)}–${hhmm(h.close_minute)}`}</span>
            </span>
            <Button variant="secondary" onClick={() => del.mutate(h.id)}>Remove</Button>
          </li>
        ))}
        {q.data?.length === 0 && <li className="py-1.5 text-slate-500">No holidays yet.</li>}
      </ul>
      <ErrorMsg error={add.error ?? del.error} />
      <form className="mt-2 flex flex-wrap items-end gap-3" onSubmit={(e) => { e.preventDefault(); add.mutate(); }}>
        <Field label="Date"><input className={inputCls} type="date" required value={f.on_date} onChange={(e) => setF({ ...f, on_date: e.target.value })} /></Field>
        <Field label="Name"><input className={inputCls} required value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
        <label className="flex items-center gap-1 pb-2 text-sm"><input type="checkbox" checked={f.short} onChange={(e) => setF({ ...f, short: e.target.checked })} />Half day</label>
        {f.short && (
          <>
            <Field label="Opens"><input className={inputCls} type="time" value={f.open} onChange={(e) => setF({ ...f, open: e.target.value })} /></Field>
            <Field label="Closes"><input className={inputCls} type="time" value={f.close} onChange={(e) => setF({ ...f, close: e.target.value })} /></Field>
          </>
        )}
        <Button type="submit">Add holiday</Button>
      </form>
    </Card>
  );
}
