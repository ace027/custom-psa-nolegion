import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { format } from "date-fns";
import { ReactNode, useEffect, useId, useRef, useState } from "react";
import { api, type Page, type Ticket } from "../api";
import { Button, ErrorMsg, Field, inputCls } from "../ui";
import { createAppointment, listStaff, schedulingKeys, type Appointment } from "./api";
import { fromBoardDate, toBoardDate } from "./zone";

/* ---- Shared by the booking and edit dialogs ---- */

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/** A modal dialog: Esc closes, focus moves to the first field on open, Tab stays inside, and focus returns on close. */
export function Modal({ title, onClose, children }: { title: string; onClose(): void; children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  const titleId = useId();
  useEffect(() => {
    const back = document.activeElement as HTMLElement | null;
    const first = ref.current?.querySelector<HTMLElement>("input:not([disabled]), select:not([disabled]), textarea:not([disabled])")
      ?? ref.current?.querySelector<HTMLElement>(FOCUSABLE);
    first?.focus();
    return () => back?.focus?.();
  }, []);
  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") {
      e.stopPropagation();
      onClose();
      return;
    }
    if (e.key !== "Tab" || !ref.current) return;
    const items = [...ref.current.querySelectorAll<HTMLElement>(FOCUSABLE)];
    if (!items.length) return;
    const [first, last] = [items[0], items[items.length - 1]];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  };
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-slate-900/40 p-4" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onKeyDown={onKeyDown}
        className="max-h-[90vh] w-full max-w-lg space-y-3 overflow-y-auto rounded-xl border border-slate-200 bg-surface p-5 shadow-card"
      >
        <h2 id={titleId} className="text-lg font-semibold">{title}</h2>
        {children}
      </div>
    </div>
  );
}

export interface SlotFields {
  date: string; // yyyy-MM-dd in the board zone
  start: string; // HH:mm
  end: string; // HH:mm
}

/** Board-zone date and time fields for a pair of UTC instants. */
export function slotFields(startsAt: string, endsAt: string, zone: string): SlotFields {
  const s = toBoardDate(startsAt, zone);
  const e = toBoardDate(endsAt, zone);
  return { date: format(s, "yyyy-MM-dd"), start: format(s, "HH:mm"), end: format(e, "HH:mm") };
}

/** Board ("fake local") start and end for the fields. An End at or before Start means the next day. */
export function slotDates(f: SlotFields): { start: Date; end: Date; nextDay: boolean } | null {
  const d = /^(\d{4})-(\d{2})-(\d{2})$/.exec(f.date);
  const s = /^(\d{2}):(\d{2})$/.exec(f.start);
  const e = /^(\d{2}):(\d{2})$/.exec(f.end);
  if (!d || !s || !e) return null;
  const [y, m, day] = [Number(d[1]), Number(d[2]) - 1, Number(d[3])];
  const start = new Date(y, m, day, Number(s[1]), Number(s[2]));
  let end = new Date(y, m, day, Number(e[1]), Number(e[2]));
  const nextDay = end <= start;
  if (nextDay) end = new Date(y, m, day + 1, Number(e[1]), Number(e[2]));
  return { start, end, nextDay };
}

export function SlotInputs({ value, onChange, disabled }: { value: SlotFields; onChange(v: SlotFields): void; disabled?: boolean }) {
  const nextDay = slotDates(value)?.nextDay;
  return (
    <div className="grid grid-cols-3 gap-2">
      <Field label="Date"><input type="date" required disabled={disabled} className={inputCls} value={value.date} onChange={(e) => onChange({ ...value, date: e.target.value })} /></Field>
      <Field label="Start"><input type="time" required step={300} disabled={disabled} className={inputCls} value={value.start} onChange={(e) => onChange({ ...value, start: e.target.value })} /></Field>
      <Field label="End"><input type="time" required step={300} disabled={disabled} className={inputCls} value={value.end} onChange={(e) => onChange({ ...value, end: e.target.value })} /></Field>
      {nextDay && <p className="col-span-full text-xs text-slate-500">Ends the next day.</p>}
    </div>
  );
}

/* ---- Booking ---- */

export interface BookingDialogProps {
  open: boolean;
  onClose(): void;
  /** `start` and `end` are board dates (wall clock in `zone`), as the calendar hands them out. */
  initial?: { techId?: number; start?: Date; end?: Date; ticketId?: number };
  zone: string;
  /** Called with the new appointment (and its conflicts) after a 201. */
  onBooked?(a: Appointment): void;
}

export function BookingDialog(props: BookingDialogProps) {
  if (!props.open) return null; // remount on each open so the form starts from `initial`
  return <BookingForm {...props} />;
}

function defaultSlot(initial: BookingDialogProps["initial"], zone: string): SlotFields {
  if (initial?.start) {
    const end = initial.end ?? new Date(initial.start.getTime() + 3600_000);
    return { date: format(initial.start, "yyyy-MM-dd"), start: format(initial.start, "HH:mm"), end: format(end, "HH:mm") };
  }
  const now = toBoardDate(new Date().toISOString(), zone);
  const start = new Date(now.getFullYear(), now.getMonth(), now.getDate(), now.getHours() + 1);
  const end = new Date(start.getTime() + 3600_000);
  return { date: format(start, "yyyy-MM-dd"), start: format(start, "HH:mm"), end: format(end, "HH:mm") };
}

const ticketLabel = (t: Ticket): string => `#${t.number} ${t.subject}${t.organization_name ? ` (${t.organization_name})` : ""}`;

function BookingForm({ onClose, initial, zone, onBooked }: BookingDialogProps) {
  const qc = useQueryClient();
  const staff = useQuery({ queryKey: schedulingKeys.staff(), queryFn: listStaff });
  const [q, setQ] = useState("");
  const [ticket, setTicket] = useState<Ticket | null>(null);
  const [techId, setTechId] = useState(initial?.techId ? String(initial.techId) : "");
  const [slot, setSlot] = useState<SlotFields>(() => defaultSlot(initial, zone));
  const [notes, setNotes] = useState("");
  const [visible, setVisible] = useState(true);
  const [formError, setFormError] = useState("");
  const fixedTicket = initial?.ticketId;

  // Same endpoint and filters as the Tickets page.
  const params = new URLSearchParams({ limit: "10", offset: "0", sort: "updated", descending: "true", open_only: "true" });
  if (q.trim()) params.set("q", q.trim());
  const search = useQuery({
    queryKey: ["tickets", params.toString()],
    queryFn: () => api<Page<Ticket>>(`/tickets?${params}`),
    enabled: !fixedTicket && !ticket && q.trim().length > 0,
  });

  const book = useMutation({
    mutationFn: createAppointment,
    onSuccess: (a) => {
      qc.invalidateQueries({ queryKey: schedulingKeys.all });
      onBooked?.(a);
      onClose();
    },
  });

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    setFormError("");
    const ticketId = fixedTicket ?? ticket?.id;
    if (!ticketId) return setFormError("Pick a ticket.");
    if (!techId) return setFormError("Pick a tech.");
    const dates = slotDates(slot);
    if (!dates) return setFormError("Enter a date, a start and an end.");
    book.mutate({
      ticket_id: ticketId,
      tech_id: Number(techId),
      starts_at: fromBoardDate(dates.start, zone),
      ends_at: fromBoardDate(dates.end, zone),
      notes: notes.trim() || null,
      client_visible: visible,
    });
  };

  return (
    <Modal title="New booking" onClose={onClose}>
      <form className="space-y-3" onSubmit={submit}>
        {!fixedTicket && (
          ticket ? (
            <div className="flex items-center justify-between gap-2 rounded-lg border border-slate-200 px-3 py-2 text-sm">
              <span>Ticket: <b>{ticketLabel(ticket)}</b></span>
              <Button type="button" variant="secondary" onClick={() => setTicket(null)}>Change ticket</Button>
            </div>
          ) : (
            <div>
              <Field label="Ticket">
                <input type="search" className={inputCls} placeholder="Search subject or #" value={q} onChange={(e) => setQ(e.target.value)} />
              </Field>
              {search.isFetching && <p className="mt-1 text-xs text-slate-500">Searching…</p>}
              <ErrorMsg error={search.error} />
              {search.data && (
                <ul aria-label="Ticket results" className="mt-1 max-h-48 overflow-y-auto rounded-lg border border-slate-200">
                  {search.data.items.length === 0 && <li className="px-3 py-2 text-sm text-slate-500">No open tickets match.</li>}
                  {search.data.items.map((t) => (
                    <li key={t.id}>
                      <button type="button" className="block w-full px-3 py-1.5 text-left text-sm hover:bg-slate-100" onClick={() => setTicket(t)}>{ticketLabel(t)}</button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )
        )}
        <Field label="Tech">
          <select className={inputCls} required value={techId} onChange={(e) => setTechId(e.target.value)}>
            <option value="">Select…</option>
            {staff.data?.map((s) => <option key={s.id} value={s.id}>{s.display_name}</option>)}
          </select>
        </Field>
        <SlotInputs value={slot} onChange={setSlot} />
        <p className="text-xs text-slate-500">Times in {zone}</p>
        <Field label="Notes"><textarea className={inputCls} value={notes} onChange={(e) => setNotes(e.target.value)} /></Field>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={visible} onChange={(e) => setVisible(e.target.checked)} />Visible to client</label>
        {formError && <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{formError}</p>}
        <ErrorMsg error={book.error} />
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>Close</Button>
          <Button type="submit" disabled={book.isPending}>Book</Button>
        </div>
      </form>
    </Modal>
  );
}
