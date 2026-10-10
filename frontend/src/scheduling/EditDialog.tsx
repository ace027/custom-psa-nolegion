import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { Button, ErrorMsg, Field, inputCls } from "../ui";
import { cancelAppointment, getAppointment, retryErrorText, schedulingKeys, useRetrySync, type Appointment, type AppointmentPatch, type AppointmentSync, type StaffUser } from "./api";
import { conflictLabel, dropPatch } from "./board";
import { Modal, SlotInputs, slotDates, slotFields, type SlotFields } from "./BookingDialog";

export interface EditDialogProps {
  appointment: Appointment;
  zone: string;
  staff: StaffUser[];
  /** Without schedule:write the fields are disabled and there is no Save or Cancel appointment. */
  canWrite: boolean;
  onClose(): void;
  /** Sends the PATCH (the board's optimistic move mutation, with its Undo toast). Only changed fields are passed. */
  onSave(patch: AppointmentPatch): void;
  onCancelled?(a: Appointment): void;
}

export function EditDialog({ appointment: a, zone, staff, canWrite, onClose, onSave, onCancelled }: EditDialogProps) {
  const qc = useQueryClient();
  const [techId, setTechId] = useState(String(a.tech_id));
  const [slot, setSlot] = useState<SlotFields>(() => slotFields(a.starts_at, a.ends_at, zone));
  const [notes, setNotes] = useState(a.notes ?? "");
  const [formError, setFormError] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [reason, setReason] = useState("");

  const cancel = useMutation({
    mutationFn: () => cancelAppointment(a.id, reason.trim() || undefined),
    onSuccess: (c) => {
      qc.invalidateQueries({ queryKey: schedulingKeys.all });
      onCancelled?.(c);
      onClose();
    },
  });

  const [sync, setSync] = useState<AppointmentSync | undefined>(a.sync);
  const [retryError, setRetryError] = useState("");
  const retry = useRetrySync({
    onSuccess: (updated) => { setRetryError(""); setSync(updated.sync); },
    onError: (e) => {
      setRetryError(retryErrorText(e));
      // Someone else already retried it: show where it stands now.
      getAppointment(a.id).then((fresh) => setSync(fresh.sync)).catch(() => undefined);
    },
  });
  const syncLine: string | null =
    !sync || sync.state === "off" ? null
    : sync.state === "synced" ? "In Outlook"
    : sync.state === "pending" ? "Waiting to sync"
    : sync.state === "failed" ? `Outlook sync failed: ${sync.last_error ?? "unknown error"}`
    : "Not synced: past appointment";

  const save = (e: React.FormEvent) => {
    e.preventDefault();
    setFormError("");
    const dates = slotDates(slot);
    if (!dates) return setFormError("Enter a date, a start and an end.");
    const patch: AppointmentPatch = dropPatch(a, { start: dates.start, end: dates.end, resourceId: Number(techId) }, zone) ?? {};
    const newNotes = notes.trim() || null;
    if (newNotes !== (a.notes ?? null)) patch.notes = newNotes;
    if (Object.keys(patch).length) onSave(patch);
    onClose();
  };

  // A tech who is no longer bookable still shows by name.
  const techs = staff.some((s) => s.id === a.tech_id) ? staff : [...staff, { id: a.tech_id, display_name: a.tech_name ?? `User ${a.tech_id}`, role: "tech" as const }];
  const ticketText = `#${a.ticket_number ?? a.ticket_id} ${a.ticket_subject ?? ""}`.trim();

  return (
    <Modal title="Appointment" onClose={onClose}>
      <form className="space-y-3" onSubmit={save}>
        <p className="text-sm">
          Ticket <Link className="font-medium text-blue-700 hover:underline" to={`/tickets/${a.ticket_id}`}>{ticketText}</Link>
          {a.organization_name && <span className="text-slate-500"> ({a.organization_name})</span>}
        </p>
        {syncLine && (
          <div className="text-sm" data-testid="sync-line">
            <p className={sync?.state === "failed" ? "text-red-700" : "text-slate-600"}>
              {sync?.state === "failed" && <span aria-hidden>✖ </span>}{syncLine}
            </p>
            {sync?.state === "failed" && canWrite && (
              <Button type="button" variant="secondary" className="mt-1 [@media(pointer:coarse)]:min-h-[44px]" disabled={retry.isPending} onClick={() => { setRetryError(""); retry.mutate(a.id); }}>Retry Outlook sync</Button>
            )}
            {retryError && <p role="alert" className="mt-1 text-red-700">{retryError}</p>}
          </div>
        )}
        {a.conflicts.length > 0 && (
          <div className="rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900">
            <p className="font-medium">Conflicts</p>
            <ul className="list-disc pl-5">{a.conflicts.map((c, i) => <li key={i}>{conflictLabel(c.kind)}</li>)}</ul>
          </div>
        )}
        <Field label="Tech">
          <select className={inputCls} disabled={!canWrite} value={techId} onChange={(e) => setTechId(e.target.value)}>
            {techs.map((s) => <option key={s.id} value={s.id}>{s.display_name}</option>)}
          </select>
        </Field>
        <SlotInputs value={slot} onChange={setSlot} disabled={!canWrite} />
        <p className="text-xs text-slate-500">Times in {zone}</p>
        <Field label="Notes"><textarea className={inputCls} disabled={!canWrite} value={notes} onChange={(e) => setNotes(e.target.value)} /></Field>
        {formError && <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{formError}</p>}
        <ErrorMsg error={cancel.error} />
        {canWrite && confirming && (
          <div className="space-y-2 rounded-lg border border-red-200 p-3">
            <Field label="Reason (optional)"><input className={inputCls} value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
            <div className="flex gap-2">
              <Button type="button" variant="danger" disabled={cancel.isPending} onClick={() => cancel.mutate()}>Confirm cancel</Button>
              <Button type="button" variant="secondary" onClick={() => setConfirming(false)}>Keep appointment</Button>
            </div>
          </div>
        )}
        <div className="flex flex-wrap justify-end gap-2">
          {canWrite && !confirming && <Button type="button" variant="danger" onClick={() => setConfirming(true)}>Cancel appointment</Button>}
          <Button type="button" variant="secondary" onClick={onClose}>Close</Button>
          {canWrite && <Button type="submit">Save</Button>}
        </div>
      </form>
    </Modal>
  );
}
