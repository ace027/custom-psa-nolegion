import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { format, getDay, parse, startOfWeek } from "date-fns";
import { enUS } from "date-fns/locale/en-US";
import { useEffect, useMemo, useRef, useState } from "react";
import { Calendar, dateFnsLocalizer, type EventProps, type Formats, type SlotInfo, type View } from "react-big-calendar";
import dndModule, { type EventInteractionArgs } from "react-big-calendar/lib/addons/dragAndDrop";
import "react-big-calendar/lib/css/react-big-calendar.css";
import "react-big-calendar/lib/addons/dragAndDrop/styles.css";
import { useSearchParams } from "react-router-dom";
import { can, useMe } from "../auth";
import {
  cancelAppointment,
  getAvailability,
  getOrgTimezone,
  getSchedule,
  listAppointments,
  listStaff,
  schedulingKeys,
  updateAppointment,
  type Appointment,
  type AppointmentListParams,
  type AppointmentPatch,
  type StaffUser,
} from "../scheduling/api";
import {
  backgroundBlocks,
  conflictLabel,
  dropPatch,
  moveSummary,
  toEvents,
  toResources,
  undoPatch,
  type BackgroundBlock,
  type BoardEvent,
  type BoardResource,
} from "../scheduling/board";
import { BookingDialog } from "../scheduling/BookingDialog";
import "../scheduling/dispatch.css";
import { EditDialog } from "../scheduling/EditDialog";
import { formatInZone, zoneDayRange, zoneWeekRange } from "../scheduling/zone";
import { Button, ErrorMsg } from "../ui";

/* ---- Calendar setup ---- */

const localizer = dateFnsLocalizer({
  format,
  parse,
  startOfWeek: (d: Date) => startOfWeek(d, { weekStartsOn: 1 }), // matches zoneWeekRange (Monday)
  getDay,
  locales: { "en-US": enUS },
});

interface ShadeItem extends BackgroundBlock {
  id: string;
  title: string;
  shade: true;
}
type CalItem = BoardEvent | ShadeItem;
const isShade = (e: CalItem): e is ShadeItem => "shade" in e;

// The Vite dev server hands this CJS module over as its whole exports object; the build and vitest unwrap it.
const withDragAndDrop =
  (dndModule as unknown as { default?: typeof dndModule }).default ?? dndModule;
const DnDCalendar = withDragAndDrop<CalItem, BoardResource>(Calendar);

const SHADE_CLASS: Record<BackgroundBlock["kind"], string> = { off_hours: "shade-off", time_off: "shade-timeoff", time_off_pending: "shade-pending" };
const SHADE_LABEL: Record<BackgroundBlock["kind"], string> = { off_hours: "Off hours", time_off: "Time off", time_off_pending: "Pending" };

const hhmm = (d: Date): string => format(d, "HH:mm");
const formats: Formats = {
  timeGutterFormat: "HH:mm",
  dayFormat: "EEE d MMM",
  dayHeaderFormat: "EEEE d MMMM yyyy",
  eventTimeRangeFormat: ({ start, end }) => `${hhmm(start)}–${hhmm(end)}`,
  selectRangeFormat: ({ start, end }) => `${hhmm(start)}–${hhmm(end)}`,
};

function EventBlock({ event }: EventProps<CalItem>) {
  if (isShade(event)) return event.kind === "off_hours" ? null : <span className="shade-label">{event.title}</span>;
  return (
    <span className="dispatch-event">
      <span className="dispatch-event-title">
        {event.conflicts.length > 0 && <span role="img" aria-label="Has conflicts" className="dispatch-warn">⚠</span>}
        <span>{event.title}</span>
      </span>
      <span className="dispatch-event-time">{hhmm(event.start)}–{hhmm(event.end)}</span>
    </span>
  );
}

/* ---- Day helpers (YYYY-MM-DD strings, zone-free) ---- */

const DAY = /^\d{4}-\d{2}-\d{2}$/;
function shiftDay(day: string, n: number): string {
  const [y, m, d] = day.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d + n)).toISOString().slice(0, 10);
}
function boardDay(day: string): Date {
  const [y, m, d] = day.split("-").map(Number);
  return new Date(y, m - 1, d);
}
const todayIn = (zone: string): string => formatInZone(new Date().toISOString(), zone, "yyyy-MM-dd");

interface Toast {
  id: number;
  text: string;
  undo?: () => void;
}
interface MoveVars {
  before: Appointment;
  patch: AppointmentPatch;
  undo?: boolean;
}

const uniqueLabels = (a: Appointment): string[] => [...new Set(a.conflicts.map((c) => conflictLabel(c.kind)))];

export default function Dispatch() {
  const { data: me } = useMe();
  const canWrite = can(me, "schedule:write");
  const qc = useQueryClient();
  const [params, setParams] = useSearchParams();

  const staff = useQuery({ queryKey: schedulingKeys.staff(), queryFn: listStaff });
  const orgZone = useQuery({ queryKey: schedulingKeys.orgTimezone(), queryFn: getOrgTimezone });
  const staffList: StaffUser[] = staff.data ?? [];

  const view: "day" | "week" = params.get("view") === "week" ? "week" : "day";
  const week = view === "week";
  const dateParam = params.get("date");
  const date = dateParam && DAY.test(dateParam) ? dateParam : orgZone.data ? todayIn(orgZone.data) : null;
  const techParam = Number(params.get("tech"));
  const tech = week
    ? staff.data?.find((s) => s.id === techParam)?.id ?? staff.data?.[0]?.id ?? null
    : null;

  const updateParams = (changes: Record<string, string | null>) => {
    const next = new URLSearchParams(params);
    for (const [k, v] of Object.entries(changes)) {
      if (v === null) next.delete(k);
      else next.set(k, v);
    }
    setParams(next, { replace: true });
  };

  // Week view renders in the tech's own zone. Reading another user's schedule needs timeoff:approve,
  // so on a 403 the zone comes from the availability row (schedule:read) instead.
  const schedule = useQuery({
    queryKey: schedulingKeys.schedule(tech ?? 0),
    queryFn: () => getSchedule(tech!),
    enabled: week && tech != null,
    retry: false,
  });
  const probe = date ? zoneDayRange(date, "UTC") : { from: "", to: "" };
  const techZone = useQuery({
    queryKey: schedulingKeys.availability({ ...probe, userIds: [tech ?? 0] }),
    queryFn: () => getAvailability({ ...probe, userIds: [tech!] }),
    enabled: week && tech != null && !!date && schedule.isError,
    select: (rows) => rows[0]?.timezone ?? null,
  });
  const zone: string | undefined = week
    ? schedule.data?.timezone ?? (schedule.isError ? techZone.data ?? (techZone.isError ? orgZone.data : undefined) : undefined)
    : orgZone.data;

  const range = zone && date ? (week ? zoneWeekRange(date, zone) : zoneDayRange(date, zone)) : null;
  const apptParams: AppointmentListParams | null = range
    ? week
      ? { from: range.from, to: range.to, withConflicts: true, techId: tech ?? undefined }
      : { from: range.from, to: range.to, withConflicts: true }
    : null;
  const apptKey = apptParams ? schedulingKeys.appointments(apptParams) : schedulingKeys.all;
  const appts = useQuery({
    queryKey: apptKey,
    queryFn: () => listAppointments(apptParams!),
    enabled: !!apptParams && (!week || tech != null),
  });
  const availParams = range ? { from: range.from, to: range.to, userIds: week && tech != null ? [tech] : undefined } : null;
  const avail = useQuery({
    queryKey: availParams ? schedulingKeys.availability(availParams) : schedulingKeys.all,
    queryFn: () => getAvailability(availParams!),
    enabled: !!availParams && (!week || tech != null),
  });

  /* ---- Feedback: alert for failures, toast with Undo for changes ---- */
  const [alert, setAlert] = useState<string | null>(null);
  const [toast, setToast] = useState<Toast | null>(null);
  const toastSeq = useRef(0);
  const showToast = (text: string, undo?: () => void) => setToast({ id: ++toastSeq.current, text, undo });
  // The toast holds the only Undo, so it stays while hovered or focused and can be dismissed.
  const [toastHeld, setToastHeld] = useState(false);
  useEffect(() => {
    if (!toast) { setToastHeld(false); return; }
    if (toastHeld) return;
    const t = setTimeout(() => setToast(null), 15000);
    return () => clearTimeout(t);
  }, [toast, toastHeld]);

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["scheduling", "appointments"] });
    qc.invalidateQueries({ queryKey: ["scheduling", "availability"] });
  };

  const move = useMutation({
    mutationFn: (v: MoveVars) => updateAppointment(v.before.id, v.patch),
    onMutate: async (v) => {
      setAlert(null);
      setToast(null);
      await qc.cancelQueries({ queryKey: apptKey });
      const snapshot = qc.getQueryData<Appointment[]>(apptKey);
      qc.setQueryData<Appointment[]>(apptKey, (old) => old?.map((x) => (x.id === v.before.id ? { ...x, ...v.patch } : x)));
      return { snapshot, key: apptKey };
    },
    onError: (err, _v, ctx) => {
      if (ctx) qc.setQueryData(ctx.key, ctx.snapshot);
      setAlert(err.message);
    },
    onSuccess: (after, v, ctx) => {
      if (ctx) qc.setQueryData<Appointment[]>(ctx.key, (old) => old?.map((x) => (x.id === after.id ? after : x)));
      if (v.undo) return showToast("Change undone");
      const notesChanged = (v.before.notes ?? null) !== (after.notes ?? null);
      const summary = moveSummary(v.before, after, staffList, zone!);
      const text = [summary === "No change" && notesChanged ? "Notes updated" : summary, ...uniqueLabels(after)].join(" · ");
      const back: AppointmentPatch = { ...undoPatch(v.before, after), ...(notesChanged ? { notes: v.before.notes } : {}) };
      showToast(text, () => move.mutate({ before: after, patch: back, undo: true }));
    },
    onSettled: refresh,
  });

  const undoBooking = useMutation({
    mutationFn: (id: number) => cancelAppointment(id, "Undone from the dispatch board"),
    onMutate: () => {
      setAlert(null);
      setToast(null);
    },
    onSuccess: () => showToast("Booking undone"),
    onError: (err) => setAlert(err.message),
    onSettled: refresh,
  });

  /* ---- Dialogs ---- */
  const [booking, setBooking] = useState<{ techId?: number; start?: Date; end?: Date } | null>(null);
  const [editing, setEditing] = useState<Appointment | null>(null);

  /* ---- Calendar data ---- */
  const resources = useMemo(() => toResources(staff.data ?? []), [staff.data]);
  const events: BoardEvent[] = useMemo(() => {
    if (!zone || !appts.data) return [];
    const shown = appts.data.filter((a) => a.status !== "cancelled" && (!week || a.tech_id === tech));
    return toEvents(shown, zone);
  }, [appts.data, zone, week, tech]);
  const shades: ShadeItem[] = useMemo(() => {
    if (!zone || !range || !avail.data) return [];
    const rows = week ? avail.data.filter((r) => r.user_id === tech) : avail.data;
    return backgroundBlocks(rows, zone, range).map((b, i) => ({ ...b, id: `shade-${i}`, title: SHADE_LABEL[b.kind], shade: true as const }));
  }, [avail.data, zone, range?.from, range?.to, week, tech]);
  const techZones = useMemo(() => new Map((avail.data ?? []).map((r) => [r.user_id, r.timezone])), [avail.data]);

  const tooltip = (e: CalItem): string => {
    if (isShade(e)) return e.kind === "time_off_pending" ? "Pending time off" : e.title;
    const a = e.appointment;
    const lines = [[e.title, a.ticket_subject].filter(Boolean).join(" "), ...uniqueLabels(a)];
    const tz = techZones.get(a.tech_id);
    if (zone && tz && tz !== zone) lines.push(`Tech local: ${formatInZone(a.starts_at, tz)}–${formatInZone(a.ends_at, tz)}`);
    return lines.join("\n");
  };

  const onMove = ({ event, start, end, resourceId }: EventInteractionArgs<CalItem>) => {
    if (!canWrite || !zone || isShade(event)) return;
    const target = {
      start: new Date(start),
      end: new Date(end),
      resourceId: week || resourceId == null ? event.resourceId : Number(resourceId),
    };
    const patch = dropPatch(event.appointment, target, zone);
    if (patch) move.mutate({ before: event.appointment, patch });
  };

  const onSelectSlot = (slot: SlotInfo) => {
    if (!canWrite) return;
    const start = new Date(slot.start);
    const end = slot.action === "click" ? new Date(start.getTime() + 3600_000) : new Date(slot.end);
    setBooking({ techId: week ? tech ?? undefined : slot.resourceId != null ? Number(slot.resourceId) : undefined, start, end });
  };
  const openEvent = (e: CalItem) => {
    if (!isShade(e)) setEditing(e.appointment);
  };

  /* ---- Render ---- */
  const loadError = staff.error ?? orgZone.error ?? appts.error ?? avail.error;
  const header = (
    <div className="flex flex-wrap items-center justify-between gap-2">
      <h1 className="text-2xl font-bold tracking-tight">Dispatch</h1>
      {!canWrite && me && <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-semibold text-slate-600">View only</span>}
    </div>
  );
  if (staff.isLoading || orgZone.isLoading) return <div className="space-y-4">{header}<p>Loading…</p></div>;
  if (staff.data && staff.data.length === 0) {
    return <div className="space-y-4">{header}<p className="rounded-lg border border-slate-200 bg-surface p-6 text-slate-500">No active admins or techs</p></div>;
  }

  const hours = range ? Math.round((Date.parse(range.to) - Date.parse(range.from)) / 3600_000) : 24;
  const step = week ? 7 : 1;

  return (
    <div className="space-y-4">
      {header}
      <div className="flex flex-wrap items-end gap-2" role="toolbar" aria-label="Board controls">
        <Button variant="secondary" disabled={!zone} onClick={() => zone && updateParams({ date: todayIn(zone) })}>Today</Button>
        <Button variant="secondary" disabled={!date} onClick={() => date && updateParams({ date: shiftDay(date, -step) })}>Prev</Button>
        <Button variant="secondary" disabled={!date} onClick={() => date && updateParams({ date: shiftDay(date, step) })}>Next</Button>
        <label className="text-sm">
          <span className="sr-only">Go to date</span>
          <input type="date" className="rounded-lg border border-slate-300 bg-surface px-2.5 py-1.5 text-sm [@media(pointer:coarse)]:min-h-[44px]" value={date ?? ""} onChange={(e) => DAY.test(e.target.value) && updateParams({ date: e.target.value })} />
        </label>
        <div className="inline-flex overflow-hidden rounded-lg border border-slate-300" role="group" aria-label="View">
          {(["day", "week"] as const).map((v) => (
            <button key={v} type="button" aria-pressed={view === v} onClick={() => updateParams({ view: v === "day" ? null : v })}
              className={`px-3 py-1.5 text-sm [@media(pointer:coarse)]:min-h-[44px] ${view === v ? "bg-blue-600 text-on-accent" : "bg-surface hover:bg-slate-100"}`}>
              {v === "day" ? "Day" : "Week"}
            </button>
          ))}
        </div>
        {week && (
          <label className="text-sm">
            <span className="mr-1 font-medium text-slate-700">Tech</span>
            <select className="rounded-lg border border-slate-300 bg-surface px-2.5 py-1.5 text-sm [@media(pointer:coarse)]:min-h-[44px]" value={tech ?? ""} onChange={(e) => updateParams({ tech: e.target.value })}>
              {staffList.map((s) => <option key={s.id} value={s.id}>{s.display_name}</option>)}
            </select>
          </label>
        )}
        {zone && <span className="rounded-full bg-blue-50 px-2.5 py-1 text-xs font-semibold text-blue-700">Times in {zone}</span>}
        {canWrite && <Button className="ml-auto" disabled={!zone} onClick={() => setBooking({ techId: tech ?? undefined })}>New booking</Button>}
      </div>
      <ul className="dispatch-legend" aria-label="Legend">
        <li><span aria-hidden className="swatch shade-off" />Off hours</li>
        <li><span aria-hidden className="swatch shade-timeoff" />Time off</li>
        <li><span aria-hidden className="swatch shade-pending" />Pending time off</li>
        <li><span aria-hidden className="swatch swatch-conflict">⚠</span>Conflict</li>
      </ul>
      {!week && hours !== 24 && (
        <p className="text-sm text-amber-800">Clocks change today: this day has {hours} hours.</p>
      )}
      <ErrorMsg error={loadError} />
      {alert && (
        <div role="alert" className="flex items-start justify-between gap-2 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
          <span>{alert}</span>
          <button type="button" className="underline" onClick={() => setAlert(null)}>Dismiss</button>
        </div>
      )}
      {!zone || !date || appts.isLoading ? (
        <p>Loading…</p>
      ) : (
        <div className="dispatch-board">
          <DnDCalendar
            localizer={localizer}
            formats={formats}
            culture="en-US"
            toolbar={false}
            view={view as View}
            views={["day", "week"]}
            onView={(v) => updateParams({ view: v === "week" ? "week" : null })}
            date={boardDay(date)}
            onNavigate={(d) => updateParams({ date: format(d, "yyyy-MM-dd") })}
            events={events}
            backgroundEvents={shades}
            resources={week ? undefined : resources}
            resourceIdAccessor={(r) => r.id}
            resourceTitleAccessor={(r) => r.title}
            tooltipAccessor={tooltip}
            step={15}
            timeslots={4}
            scrollToTime={new Date(1970, 0, 1, 7)}
            eventPropGetter={(e) => ({ className: isShade(e) ? SHADE_CLASS[e.kind] : e.conflicts.length > 0 ? "has-conflict" : undefined })}
            components={{ event: EventBlock }}
            selectable={canWrite}
            resizable={canWrite}
            draggableAccessor={(e) => canWrite && !isShade(e)}
            resizableAccessor={(e) => canWrite && !isShade(e)}
            onEventDrop={onMove}
            onEventResize={onMove}
            onSelectSlot={onSelectSlot}
            onSelectEvent={openEvent}
            onKeyPressEvent={(e, ev) => {
              const key = (ev.nativeEvent as KeyboardEvent).key;
              if (key === "Enter" || key === " ") openEvent(e);
            }}
          />
        </div>
      )}
      <div role="status" aria-live="polite" className="dispatch-toast-region">
        {toast && (
          <div
            className="dispatch-toast"
            onMouseEnter={() => setToastHeld(true)}
            onMouseLeave={() => setToastHeld(false)}
            onFocus={() => setToastHeld(true)}
            onBlur={() => setToastHeld(false)}
            onKeyDown={(e) => { if (e.key === "Escape") setToast(null); }}
          >
            <span>{toast.text}</span>
            {toast.undo && <button type="button" className="font-semibold underline" onClick={toast.undo}>Undo</button>}
            <button type="button" aria-label="Dismiss notification" onClick={() => setToast(null)}>×</button>
          </div>
        )}
      </div>
      {zone && (
        <BookingDialog
          open={booking !== null}
          onClose={() => setBooking(null)}
          initial={booking ?? undefined}
          zone={zone}
          onBooked={(a) => {
            const who = staffList.find((s) => s.id === a.tech_id)?.display_name ?? a.tech_name ?? "tech";
            const text = [`Booked #${a.ticket_number ?? a.ticket_id} with ${who} at ${formatInZone(a.starts_at, zone, "EEE HH:mm")}`, ...uniqueLabels(a)].join(" · ");
            showToast(text, () => undoBooking.mutate(a.id));
          }}
        />
      )}
      {editing && zone && (
        <EditDialog
          appointment={editing}
          zone={zone}
          staff={staffList}
          canWrite={canWrite}
          onClose={() => setEditing(null)}
          onSave={(patch) => move.mutate({ before: editing, patch })}
          onCancelled={() => showToast("Appointment cancelled")}
        />
      )}
    </div>
  );
}
