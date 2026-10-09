import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Timer, api } from "../api";
import { Button, ErrorMsg } from "../ui";

export const clock = (seconds: number) => {
  const s = Math.max(0, Math.floor(seconds));
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${Math.floor(s / 3600)}:${pad(Math.floor((s % 3600) / 60))}:${pad(s % 60)}`;
};

/** The running timer, shown on every staff page so it is never forgotten. */
export default function TimerBar() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["timer"], queryFn: () => api<Timer | null>("/timer") });
  const [now, setNow] = useState(() => Date.now());
  const timer = q.data && typeof q.data === "object" && "started_at" in q.data ? q.data : null;
  useEffect(() => {
    if (!timer) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [timer]);
  const done = () => {
    qc.invalidateQueries({ queryKey: ["timer"] });
    qc.invalidateQueries({ queryKey: ["time"] });
    qc.invalidateQueries({ queryKey: ["timesheet"] });
  };
  const stop = useMutation({ mutationFn: () => api("/timer/stop", { method: "POST" }), onSuccess: done });
  const discard = useMutation({ mutationFn: () => api("/timer", { method: "DELETE" }), onSuccess: done });
  if (!timer) return null;
  const elapsed = (now - new Date(timer.started_at).getTime()) / 1000;
  return (
    <div role="status" aria-label="Running timer" className="mb-4 flex flex-wrap items-center gap-3 rounded-lg border border-blue-300 bg-blue-50 px-3 py-2 text-sm text-blue-900">
      <b className="tabular-nums">{clock(elapsed)}</b>
      <span>
        {timer.ticket_id ? <Link className="underline" to={`/tickets/${timer.ticket_id}`}>#{timer.ticket_number} {timer.ticket_subject}</Link> : timer.category_name}
        {timer.note && <span className="text-blue-700"> — {timer.note}</span>}
      </span>
      <span className="ml-auto flex gap-2">
        <Button onClick={() => stop.mutate()} disabled={stop.isPending}>Stop</Button>
        <Button variant="secondary" onClick={() => { if (window.confirm("Discard this timer without saving any time?")) discard.mutate(); }}>Discard</Button>
      </span>
      <ErrorMsg error={stop.error ?? discard.error} />
    </div>
  );
}
