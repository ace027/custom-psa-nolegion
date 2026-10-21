import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Opportunity, Quote, User, api, crmApi } from "../../api";
import { can, useMe } from "../../auth";
import { money, parseMoney, percent } from "../../money";
import { Button, Card, ErrorMsg, Field, fmt, inputCls } from "../../ui";

export default function OpportunityPage() {
  const id = useParams().id as string;
  const { data: me } = useMe();
  const write = can(me, "crm:write");
  const qc = useQueryClient();
  const opp = useQuery({ queryKey: ["crm", "opportunity", id], queryFn: () => crmApi.opportunity(id) });
  const stages = useQuery({ queryKey: ["crm", "stages"], queryFn: crmApi.stages });
  const o = opp.data;
  const done = (x: Opportunity) => {
    qc.setQueryData(["crm", "opportunity", id], x);
    qc.invalidateQueries({ queryKey: ["crm"], predicate: (q) => q.queryKey[1] !== "opportunity" });
  };
  const [lost, setLost] = useState<number | null>(null);
  const [reason, setReason] = useState("");
  const [bad, setBad] = useState("");
  const move = useMutation({
    mutationFn: ({ stage, why }: { stage: number; why?: string }) => crmApi.moveStage(Number(id), stage, why),
    onSuccess: (x) => { done(x); setLost(null); setReason(""); setBad(""); },
  });
  if (!o) return <ErrorMsg error={opp.error} />;
  const cols = (stages.data ?? []).filter((s) => s.active || s.id === o.stage_id).sort((a, b) => a.position - b.position);
  const closed = o.stage_kind !== "open";
  const pick = (stageId: number) => {
    if (stageId === o.stage_id) return;
    move.reset();
    const st = cols.find((s) => s.id === stageId);
    if (st?.kind === "lost") { setLost(stageId); setReason(""); } else { setLost(null); move.mutate({ stage: stageId }); }
  };
  const confirmLost = () => {
    if (lost === null) return;
    if (!reason.trim()) return setBad("Say why it was lost.");
    setBad("");
    move.mutate({ stage: lost, why: reason.trim() });
  };
  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <p><Link className="text-sm text-blue-700 hover:underline" to="/crm/pipeline">← Pipeline</Link></p>
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="text-2xl font-bold tracking-tight">{o.name}</h1>
        <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-700">{o.stage_name} · {percent(o.probability_bp)}</span>
        <span className="text-sm capitalize text-slate-500">{o.kind}</span>
      </div>
      <Card title="Details">
        <dl className="grid gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
          <dt className="text-slate-500">Client</dt><dd><Link className="text-blue-700 hover:underline" to={`/organizations/${o.organization_id}`}>{o.organization_name}</Link></dd>
          <dt className="text-slate-500">Quote</dt><dd>{o.quote_id ? <Link className="text-blue-700 hover:underline" to={`/quotes/${o.quote_id}`}>{o.quote_number}</Link> : "None linked"}</dd>
          <dt className="text-slate-500">Agreement</dt><dd>{o.agreement_id ? <Link className="text-blue-700 hover:underline" to="/billing/agreements">{o.agreement_name}</Link> : "None yet"}</dd>
          {o.closed_at && <><dt className="text-slate-500">Closed</dt><dd>{fmt(o.closed_at)}</dd></>}
          {o.lost_reason && <><dt className="text-slate-500">Lost because</dt><dd>{o.lost_reason}</dd></>}
        </dl>
      </Card>
      <Card title="Stage">
        {write ? (
          <div className="space-y-2">
            <Field label="Move to stage">
              <select className={inputCls + " max-w-xs"} value={o.stage_id} disabled={move.isPending} onChange={(e) => pick(Number(e.target.value))}>
                {cols.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            </Field>
            {lost !== null && (
              <div className="space-y-2">
                <Field label="Lost reason"><input className={inputCls} maxLength={300} value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
                {bad && <p role="alert" className="text-sm text-red-700">{bad}</p>}
                <div className="flex gap-2">
                  <Button onClick={confirmLost} disabled={move.isPending}>Mark lost</Button>
                  <Button variant="secondary" onClick={() => { setLost(null); setBad(""); }}>Cancel</Button>
                </div>
              </div>
            )}
            <ErrorMsg error={move.error} />
          </div>
        ) : <p className="text-sm">{o.stage_name}</p>}
      </Card>
      <EditCard o={o} write={write} closed={closed} onSaved={done} />
      {write && !closed && <QuoteLinkCard o={o} onLinked={done} />}
    </div>
  );
}

function EditCard({ o, write, closed, onSaved }: { o: Opportunity; write: boolean; closed: boolean; onSaved: (o: Opportunity) => void }) {
  const users = useQuery({ queryKey: ["users"], queryFn: () => api<User[]>("/users"), enabled: write });
  const init = () => ({
    name: o.name, monthly: (o.monthly_cents / 100).toFixed(2), term: String(o.term_months),
    close: o.expected_close_date ?? "", owner: o.owner_id ? String(o.owner_id) : "", notes: o.notes ?? "",
  });
  const [f, setF] = useState(init);
  useEffect(() => setF(init()), [o.id, o.updated_at]); // eslint-disable-line react-hooks/exhaustive-deps
  const [bad, setBad] = useState("");
  const save = useMutation({ mutationFn: (json: Parameters<typeof crmApi.updateOpportunity>[1]) => crmApi.updateOpportunity(o.id, json), onSuccess: onSaved });
  const readOnly = !write || closed;
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const cents = parseMoney(f.monthly);
    const months = Number(f.term);
    if (cents === null || cents < 0) return setBad("Enter the monthly amount, for example 1500.00.");
    if (!Number.isInteger(months) || months < 1 || months > 120) return setBad("Term must be 1 to 120 months.");
    setBad("");
    save.mutate({ name: f.name.trim(), monthly_cents: cents, term_months: months, expected_close_date: f.close || null, owner_id: f.owner ? Number(f.owner) : null, notes: f.notes.trim() || null });
  };
  return (
    <Card title="Deal">
      <form onSubmit={submit} className="grid gap-3 sm:grid-cols-2">
        <Field label="Name"><input className={inputCls} value={f.name} onChange={set("name")} disabled={readOnly} required /></Field>
        <Field label="Owner">
          <select className={inputCls} value={f.owner} onChange={set("owner")} disabled={readOnly}>
            <option value="">{o.owner_name && !f.owner ? o.owner_name : "Unowned"}</option>
            {(users.data ?? []).filter((u) => u.is_active && (u.role === "admin" || u.role === "tech")).map((u) => <option key={u.id} value={u.id}>{u.display_name}</option>)}
          </select>
        </Field>
        <Field label="Monthly ($)"><input className={inputCls} value={f.monthly} onChange={set("monthly")} disabled={readOnly} inputMode="decimal" /></Field>
        <Field label="Term (months)"><input className={inputCls} type="number" min={1} max={120} value={f.term} onChange={set("term")} disabled={readOnly} /></Field>
        <Field label="Expected close"><input className={inputCls} type="date" value={f.close} onChange={set("close")} disabled={readOnly} /></Field>
        <p className="self-end text-sm text-slate-600">Contract value {money((parseMoney(f.monthly) ?? 0) * (Number(f.term) || 0))}</p>
        <div className="sm:col-span-2"><Field label="Notes"><textarea className={inputCls} rows={3} value={f.notes} onChange={set("notes")} disabled={readOnly} /></Field></div>
        {!readOnly && (
          <div className="space-y-2 sm:col-span-2">
            {bad && <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{bad}</p>}
            <ErrorMsg error={save.error} />
            <Button type="submit" disabled={save.isPending}>Save</Button>
          </div>
        )}
        {write && closed && <p className="text-xs text-slate-500 sm:col-span-2">This opportunity is closed. Move it back to an open stage to edit it.</p>}
      </form>
    </Card>
  );
}

function QuoteLinkCard({ o, onLinked }: { o: Opportunity; onLinked: (o: Opportunity) => void }) {
  const [quoteId, setQuoteId] = useState("");
  const quotes = useQuery({ queryKey: ["quotes"], queryFn: () => api<Quote[]>("/quotes") });
  const link = useMutation({ mutationFn: () => crmApi.linkQuote(o.id, Number(quoteId)), onSuccess: (x) => { setQuoteId(""); onLinked(x); } });
  const mine = (quotes.data ?? []).filter((q) => q.organization_id === o.organization_id && q.id !== o.quote_id && !["declined", "cancelled"].includes(q.status));
  return (
    <Card title={o.quote_id ? "Change linked quote" : "Link a quote"}>
      <div className="flex flex-wrap items-end gap-2">
        <Field label="Quote for this client">
          <select className={inputCls + " min-w-48"} value={quoteId} onChange={(e) => setQuoteId(e.target.value)}>
            <option value="">{mine.length === 0 ? "No quotes for this client" : "Choose a quote…"}</option>
            {mine.map((q) => <option key={q.id} value={q.id}>{q.number} ({q.status})</option>)}
          </select>
        </Field>
        <Button disabled={!quoteId || link.isPending} onClick={() => link.mutate()}>Link quote</Button>
      </div>
      <p className="mt-2 text-xs text-slate-500">When the client accepts the linked quote, this opportunity is won and the agreement is attached.</p>
      <ErrorMsg error={link.error} />
    </Card>
  );
}
