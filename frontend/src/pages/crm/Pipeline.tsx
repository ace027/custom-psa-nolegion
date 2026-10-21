import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Opportunity, Stage, crmApi } from "../../api";
import { can, useMe } from "../../auth";
import { money } from "../../money";
import { Button, ErrorMsg, inputCls } from "../../ui";

export default function Pipeline() {
  const { data: me } = useMe();
  const write = can(me, "crm:write");
  const qc = useQueryClient();
  const stages = useQuery({ queryKey: ["crm", "stages"], queryFn: crmApi.stages });
  const opps = useQuery({ queryKey: ["crm", "opportunities"], queryFn: () => crmApi.opportunities() });
  // A move to a lost stage waits here until a reason is given.
  const [lost, setLost] = useState<{ opp: Opportunity; stage: Stage } | null>(null);
  const [reason, setReason] = useState("");
  const [clientError, setClientError] = useState("");
  const reasonRef = useRef<HTMLInputElement>(null);
  const selectRefs = useRef(new Map<number, HTMLSelectElement>());
  // Move focus to the reason field when the lost form appears.
  useEffect(() => {
    if (lost) reasonRef.current?.focus();
  }, [lost]);
  const move = useMutation({
    mutationFn: ({ opp, stage, why }: { opp: Opportunity; stage: Stage; why?: string }) => crmApi.moveStage(opp.id, stage.id, why),
    onSuccess: () => {
      setLost(null);
      setReason("");
      setClientError("");
      qc.invalidateQueries({ queryKey: ["crm"] });
    },
  });
  const cols = (stages.data ?? []).filter((s) => s.active).sort((a, b) => a.position - b.position);
  const all = opps.data ?? [];
  const pick = (opp: Opportunity, stageId: number) => {
    const stage = cols.find((s) => s.id === stageId);
    if (!stage || stage.id === opp.stage_id) return;
    setClientError("");
    move.reset();
    if (stage.kind === "lost") {
      setLost({ opp, stage });
      setReason("");
    } else {
      setLost(null);
      move.mutate({ opp, stage });
    }
  };
  const confirmLost = () => {
    if (!lost) return;
    if (!reason.trim()) return setClientError("Say why it was lost.");
    setClientError("");
    move.mutate({ opp: lost.opp, stage: lost.stage, why: reason.trim() });
  };
  const cancelLost = () => {
    const id = lost?.opp.id;
    setLost(null);
    setClientError("");
    move.reset();
    if (id !== undefined) setTimeout(() => selectRefs.current.get(id)?.focus(), 0);
  };
  return (
    <div className="space-y-3">
      <ErrorMsg error={stages.error ?? opps.error} />
      <ErrorMsg error={move.error} />
      {stages.data && cols.length === 0 && <p className="text-sm text-slate-500">No pipeline stages are set up. An admin can add them in Settings.</p>}
      {cols.length > 0 && all.length === 0 && !opps.isLoading && <p className="text-sm text-slate-500">No opportunities yet. Convert a lead or add one from a client page.</p>}
      <div className="grid gap-3 md:grid-cols-3 xl:grid-cols-5">
        {cols.map((col) => {
          const items = all.filter((o) => o.stage_id === col.id);
          return (
            <section key={col.id} aria-label={col.name} className="rounded-xl bg-slate-50 p-2">
              <h2 className="mb-2 px-1 text-sm font-semibold text-slate-700">{col.name} ({items.length})</h2>
              <ul className="space-y-2">
                {items.map((o) => (
                  <li key={o.id} className={`${move.isPending ? "opacity-60 " : ""}rounded-lg border border-slate-200 bg-surface p-2 text-sm shadow-card`}>
                    <Link className="font-medium text-blue-700 hover:underline" to={`/crm/opportunities/${o.id}`}>{o.name}</Link>
                    <div className="text-xs text-slate-600">{o.organization_name}</div>
                    <div className="mt-1 flex flex-wrap gap-x-3 text-xs text-slate-600">
                      <span>{money(o.monthly_cents)}/mo</span>
                      <span>{o.expected_close_date ? `Close ${o.expected_close_date}` : "No close date"}</span>
                      <span>{o.owner_name ?? "Unowned"}</span>
                    </div>
                    {write && (
                      <select
                        ref={(el) => { if (el) selectRefs.current.set(o.id, el); else selectRefs.current.delete(o.id); }}
                        aria-label={`Move ${o.name} to stage`}
                        className={`${inputCls} mt-2`}
                        value={lost && lost.opp.id === o.id ? lost.stage.id : o.stage_id}
                        disabled={move.isPending}
                        onChange={(e) => pick(o, Number(e.target.value))}
                      >
                        {cols.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                      </select>
                    )}
                    {write && lost && lost.opp.id === o.id && (
                      <div role="group" aria-label="Mark as lost" className="mt-2 space-y-2 rounded-lg border border-amber-300 bg-amber-50 p-2 text-sm">
                        <label className="block">
                          <span className="mb-1 block font-medium">Why was “{lost.opp.name}” lost?</span>
                          <input ref={reasonRef} aria-label="Lost reason" className={inputCls} maxLength={300} value={reason} onChange={(e) => setReason(e.target.value)} />
                        </label>
                        {clientError && <p role="alert" className="text-red-700">{clientError}</p>}
                        <div className="flex gap-2">
                          <Button onClick={confirmLost} disabled={move.isPending}>Mark lost</Button>
                          <Button variant="secondary" onClick={cancelLost}>Cancel</Button>
                        </div>
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            </section>
          );
        })}
      </div>
    </div>
  );
}
