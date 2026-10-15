import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { format } from "date-fns";
import { useMemo, useState } from "react";
import { can, useMe } from "../auth";
import { getOrgTimezone, listStaff, schedulingKeys } from "../scheduling/api";
import {
  WEEKDAYS,
  createOverride,
  createRotation,
  deleteOverride,
  getOnCallNow,
  getOnCallSchedule,
  listOverrides,
  listRotations,
  moveMember,
  nextWeekday,
  oncallKeys,
  updateRotation,
  weekdayOf,
  type Rotation,
} from "../scheduling/oncall";
import { formatInZone, fromBoardDate } from "../scheduling/zone";
import { Button, Card, ErrorMsg, Field, inputCls } from "../ui";

interface Draft {
  id: number | null;
  name: string;
  weekday: number;
  time: string; // HH:mm
  anchor: string; // yyyy-MM-dd
  active: boolean;
  members: number[];
}

const blankDraft = (): Draft => ({ id: null, name: "", weekday: 0, time: "09:00", anchor: nextWeekday(format(new Date(), "yyyy-MM-dd"), 0), active: true, members: [] });
const draftOf = (r: Rotation): Draft => ({
  id: r.id,
  name: r.name,
  weekday: r.handoff_weekday,
  time: r.handoff_time.slice(0, 5),
  anchor: r.anchor_date,
  active: r.active,
  members: [...r.members].sort((a, b) => a.position - b.position).map((m) => m.user_id),
});

export default function OnCall() {
  const { data: me } = useMe();
  const canWrite = can(me, "schedule:write");
  const rotations = useQuery({ queryKey: oncallKeys.rotations(), queryFn: listRotations });
  const staff = useQuery({ queryKey: schedulingKeys.staff(), queryFn: listStaff });
  const zoneQ = useQuery({ queryKey: schedulingKeys.orgTimezone(), queryFn: getOrgTimezone });
  const zone = zoneQ.data ?? "UTC";
  const list = rotations.data ?? [];
  const [draft, setDraft] = useState<Draft | null>(null);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl font-bold tracking-tight">On-call</h1>
        {!canWrite && me && <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-semibold text-slate-600">View only</span>}
        {canWrite && !draft && <Button onClick={() => setDraft(blankDraft())}>New rotation</Button>}
      </div>
      <ErrorMsg error={rotations.error} />
      {rotations.isLoading && <p>Loading…</p>}
      {rotations.data && list.length === 0 && (
        <p className="rounded-lg border border-slate-200 bg-surface p-6 text-slate-500">No rotations yet.{canWrite ? " Create one to start scheduling on-call." : ""}</p>
      )}
      {canWrite && draft && <RotationForm draft={draft} setDraft={setDraft} staff={staff.data ?? []} onDone={() => setDraft(null)} />}
      {list.map((r) => (
        <RotationCard key={r.id} rotation={r} canWrite={canWrite} zone={zone} staff={staff.data ?? []} onEdit={() => setDraft(draftOf(r))} />
      ))}
      {list.length > 0 && <ShiftTable rotations={list} zone={zone} />}
    </div>
  );
}

function RotationForm({ draft, setDraft, staff, onDone }: { draft: Draft; setDraft(d: Draft): void; staff: { id: number; display_name: string }[]; onDone(): void }) {
  const qc = useQueryClient();
  const [pick, setPick] = useState("");
  const name = (id: number) => staff.find((s) => s.id === id)?.display_name ?? `User ${id}`;
  const save = useMutation({
    mutationFn: () => {
      const body = { name: draft.name.trim(), handoff_weekday: draft.weekday, handoff_time: draft.time, anchor_date: draft.anchor, member_ids: draft.members };
      return draft.id === null ? createRotation(body) : updateRotation(draft.id, { ...body, active: draft.active });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: oncallKeys.all });
      onDone();
    },
  });
  const anchorOk = weekdayOf(draft.anchor) === draft.weekday;
  const available = staff.filter((s) => !draft.members.includes(s.id));
  return (
    <Card title={draft.id === null ? "New rotation" : "Edit rotation"}>
      <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); if (anchorOk) save.mutate(); }}>
        <div className="grid gap-3 sm:grid-cols-4">
          <Field label="Name"><input className={inputCls} required maxLength={100} value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} /></Field>
          <Field label="Handoff weekday">
            <select className={inputCls} value={draft.weekday} onChange={(e) => { const weekday = Number(e.target.value); setDraft({ ...draft, weekday, anchor: nextWeekday(draft.anchor, weekday) }); }}>
              {WEEKDAYS.map((d, i) => <option key={d} value={i}>{d}</option>)}
            </select>
          </Field>
          <Field label="Handoff time"><input className={inputCls} type="time" required value={draft.time} onChange={(e) => setDraft({ ...draft, time: e.target.value })} /></Field>
          <Field label="Anchor date"><input className={inputCls} type="date" required value={draft.anchor} onChange={(e) => setDraft({ ...draft, anchor: e.target.value })} /></Field>
        </div>
        {!anchorOk && <p role="alert" className="text-sm text-red-700">The anchor date must be a {WEEKDAYS[draft.weekday]}.</p>}
        <p className="text-xs text-slate-500">The first member is on call from the anchor date and handoff time; the rest follow in order, one week each.</p>
        <div>
          <p className="mb-1 text-sm font-medium text-slate-700">Members, in order</p>
          <ol className="divide-y divide-slate-100 text-sm">
            {draft.members.map((id, i) => (
              <li key={id} className="flex items-center justify-between gap-2 py-1">
                <span>{i + 1}. {name(id)}</span>
                <span className="flex gap-1">
                  <Button type="button" variant="secondary" aria-label={`Move ${name(id)} up`} disabled={i === 0} onClick={() => setDraft({ ...draft, members: moveMember(draft.members, i, -1) })}>Up</Button>
                  <Button type="button" variant="secondary" aria-label={`Move ${name(id)} down`} disabled={i === draft.members.length - 1} onClick={() => setDraft({ ...draft, members: moveMember(draft.members, i, 1) })}>Down</Button>
                  <Button type="button" variant="secondary" aria-label={`Remove ${name(id)}`} onClick={() => setDraft({ ...draft, members: draft.members.filter((m) => m !== id) })}>Remove</Button>
                </span>
              </li>
            ))}
            {draft.members.length === 0 && <li className="py-1 text-slate-500">No members yet.</li>}
          </ol>
          <div className="mt-2 flex items-end gap-2">
            <Field label="Add member">
              <select className={inputCls} value={pick} onChange={(e) => setPick(e.target.value)}>
                <option value="">Select…</option>
                {available.map((s) => <option key={s.id} value={s.id}>{s.display_name}</option>)}
              </select>
            </Field>
            <Button type="button" variant="secondary" disabled={!pick} onClick={() => { setDraft({ ...draft, members: [...draft.members, Number(pick)] }); setPick(""); }}>Add member</Button>
          </div>
        </div>
        {draft.id !== null && (
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={draft.active} onChange={(e) => setDraft({ ...draft, active: e.target.checked })} />Active</label>
        )}
        <ErrorMsg error={save.error} />
        <div className="flex gap-2">
          <Button type="submit" disabled={save.isPending || !anchorOk}>{draft.id === null ? "Create rotation" : "Save rotation"}</Button>
          <Button type="button" variant="secondary" onClick={onDone}>Cancel</Button>
        </div>
      </form>
    </Card>
  );
}

function RotationCard({ rotation: r, canWrite, zone, staff, onEdit }: { rotation: Rotation; canWrite: boolean; zone: string; staff: { id: number; display_name: string }[]; onEdit(): void }) {
  const qc = useQueryClient();
  const overrides = useQuery({ queryKey: oncallKeys.overrides(r.id), queryFn: () => listOverrides(r.id) });
  const [f, setF] = useState({ user: "", start: "", end: "", reason: "" });
  const now = useQuery({ queryKey: oncallKeys.now(), queryFn: getOnCallNow, retry: false });
  const holder = now.data?.find((n) => n.rotation_id === r.id);
  const [showForm, setShowForm] = useState(false);
  const [confirmId, setConfirmId] = useState<number | null>(null);
  const refresh = () => qc.invalidateQueries({ queryKey: oncallKeys.all });
  const add = useMutation({
    mutationFn: () => {
      const toIso = (v: string) => fromBoardDate(new Date(v), zone); // datetime-local parses as board wall-clock
      return createOverride(r.id, { user_id: Number(f.user), starts_at: toIso(f.start), ends_at: toIso(f.end), reason: f.reason.trim() || null });
    },
    onSuccess: () => { setF({ user: "", start: "", end: "", reason: "" }); setShowForm(false); refresh(); },
  });
  const del = useMutation({ mutationFn: (id: number) => deleteOverride(id), onSuccess: refresh });
  const members = [...r.members].sort((a, b) => a.position - b.position);
  return (
    <Card title={`${r.name}${r.active ? "" : " (inactive)"}`} actions={canWrite ? <Button variant="secondary" onClick={onEdit}>Edit {r.name}</Button> : undefined}>
      <p className="text-sm text-slate-600">
        Hands off {WEEKDAYS[r.handoff_weekday]}s at {r.handoff_time.slice(0, 5)} ({zone}), from {r.anchor_date}.
      </p>
      {holder && (
        <p className="mt-1 text-sm font-medium" data-testid="oncall-holder">
          On call now: {holder.user_name ?? "nobody"}{holder.until ? ` until ${formatInZone(holder.until, zone, "EEE d MMM HH:mm")}` : ""}
        </p>
      )}
      <p className="mt-1 text-sm">{members.length ? members.map((m, i) => `${i + 1}. ${m.name}`).join("  ") : "No members."}</p>
      <h3 className="mt-3 text-sm font-semibold">Overrides</h3>
      <ErrorMsg error={overrides.error} />
      <ul className="divide-y divide-slate-100 text-sm">
        {overrides.data?.map((o) => (
          <li key={o.id} className="flex flex-wrap items-center justify-between gap-2 py-1.5">
            <span>
              <b>{o.user_name ?? `User ${o.user_id}`}</b> {formatInZone(o.starts_at, zone, "EEE d MMM HH:mm")} to {formatInZone(o.ends_at, zone, "EEE d MMM HH:mm")}
              {o.reason && <span className="text-slate-500"> ({o.reason})</span>}
            </span>
            {canWrite && (confirmId === o.id ? (
              <span className="flex gap-1">
                <Button variant="secondary" aria-label={`Confirm delete override for ${o.user_name ?? o.user_id}`} disabled={del.isPending} onClick={() => del.mutate(o.id, { onSettled: () => setConfirmId(null) })}>Confirm delete</Button>
                <Button variant="secondary" disabled={del.isPending} onClick={() => setConfirmId(null)}>Cancel</Button>
              </span>
            ) : (
              <Button variant="secondary" aria-label={`Delete override for ${o.user_name ?? o.user_id}`} disabled={del.isPending} onClick={() => setConfirmId(o.id)}>Delete</Button>
            ))}
          </li>
        ))}
        {overrides.data?.length === 0 && <li className="py-1.5 text-slate-500">No overrides.</li>}
      </ul>
      <ErrorMsg error={del.error} />
      {canWrite && !showForm && <Button className="mt-2" variant="secondary" onClick={() => setShowForm(true)}>Add override</Button>}
      {canWrite && showForm && (
        <form className="mt-2 flex flex-wrap items-end gap-3" onSubmit={(e) => { e.preventDefault(); add.mutate(); }}>
          <Field label="Override user">
            <select className={inputCls} required value={f.user} onChange={(e) => setF({ ...f, user: e.target.value })}>
              <option value="">Select…</option>
              {staff.map((s) => <option key={s.id} value={s.id}>{s.display_name}</option>)}
            </select>
          </Field>
          <Field label="Override start"><input className={inputCls} type="datetime-local" required value={f.start} onChange={(e) => setF({ ...f, start: e.target.value })} /></Field>
          <Field label="Override end"><input className={inputCls} type="datetime-local" required value={f.end} onChange={(e) => setF({ ...f, end: e.target.value })} /></Field>
          <Field label="Reason"><input className={inputCls} maxLength={200} value={f.reason} onChange={(e) => setF({ ...f, reason: e.target.value })} /></Field>
          <Button type="submit" disabled={add.isPending}>Save override</Button>
          <Button type="button" variant="secondary" onClick={() => setShowForm(false)}>Cancel</Button>
        </form>
      )}
      <ErrorMsg error={add.error} />
      <p className="mt-1 text-xs text-slate-500">Override times are in {zone}.</p>
    </Card>
  );
}

function ShiftTable({ rotations, zone }: { rotations: Rotation[]; zone: string }) {
  // Fixed at mount (to the hour) so the query key does not change on every render.
  const range = useMemo(() => {
    const from = new Date(Math.floor(Date.now() / 3600_000) * 3600_000);
    return { from: from.toISOString(), to: new Date(from.getTime() + 28 * 86400_000).toISOString() };
  }, []);
  const q = useQuery({ queryKey: oncallKeys.schedule(range.from, range.to), queryFn: () => getOnCallSchedule(range.from, range.to) });
  const names = Object.fromEntries(rotations.map((r) => [r.id, r.name]));
  const shifts = [...(q.data ?? [])].sort((a, b) => Date.parse(a.starts_at) - Date.parse(b.starts_at));
  return (
    <Card title="Next 4 weeks">
      <ErrorMsg error={q.error} />
      {q.data && shifts.length === 0 && <p className="text-sm text-slate-500">No shifts in the next 4 weeks.</p>}
      {shifts.length > 0 && (
        <table className="w-full text-left text-sm">
          <thead className="text-slate-500"><tr><th>Rotation</th><th>Who</th><th>From</th><th>Until</th><th>Source</th></tr></thead>
          <tbody>
            {shifts.map((s, i) => (
              <tr key={i} className="border-t border-slate-100">
                <td>{names[s.rotation_id] ?? s.rotation_id}</td>
                <td>{s.user_name ?? `User ${s.user_id}`}</td>
                <td>{formatInZone(s.starts_at, zone, "EEE d MMM HH:mm")}</td>
                <td>{formatInZone(s.ends_at, zone, "EEE d MMM HH:mm")}</td>
                <td>{s.source === "override" ? "Override" : "Rotation"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Card>
  );
}
