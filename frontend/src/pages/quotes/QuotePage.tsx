import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Quote, api } from "../../api";
import { can, useMe } from "../../auth";
import { money, parseMoney, percent } from "../../money";
import { Button, Card, ErrorMsg, Field, inputCls } from "../../ui";
import { Badge } from "./QuotesList";

export default function QuotePage() {
  const id = useParams().id as string;
  const { data: me } = useMe();
  const write = can(me, "quote:write");
  const manage = can(me, "quote:manage");
  const nav = useNavigate();
  const qc = useQueryClient();
  const quote = useQuery({ queryKey: ["quote", id], queryFn: () => api<Quote>(`/quotes/${id}`) });
  const [price, setPrice] = useState("");
  const [reason, setReason] = useState("");
  const [note, setNote] = useState("");
  const [email, setEmail] = useState(false);
  const [to, setTo] = useState("");
  const [start, setStart] = useState("");
  const done = (q: Quote) => { qc.setQueryData(["quote", id], q); qc.invalidateQueries({ queryKey: ["quotes"] }); };
  const act = useMutation({
    mutationFn: ({ path, json, method = "POST" }: { path: string; json?: unknown; method?: string }) => api<Quote>(`/quotes/${id}${path}`, { method, json }),
    onSuccess: (q, v) => { done(q); if (v.path === "/revise") nav(`/quotes/${q.id}`); },
  });
  const q = quote.data;
  if (!q) return <ErrorMsg error={quote.error} />;
  const adjusted = q.final_price_cents !== q.computed_price_cents;
  const editable = ["draft", "needs_approval", "approved"].includes(q.status);
  const adjust = () => {
    const cents = parseMoney(price);
    if (cents === null) return act.reset();
    act.mutate({ path: "", method: "PATCH", json: { final_price_cents: cents, adjustment_reason: reason || null } });
  };
  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <p><Link className="text-sm text-blue-700 hover:underline" to="/quotes">← Quotes</Link></p>
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="text-xl font-semibold">{q.number}{q.version > 1 ? ` v${q.version}` : ""}: {q.organization_name}</h1>
        <Badge status={q.status} expired={q.is_expired} />
        {q.kind === "reprice" && <span className="text-sm text-slate-500">reprice from {q.effective_date}</span>}
      </div>
      <Card title="Monthly flat fee" actions={<a className="text-sm text-blue-700 hover:underline" href={`/api/quotes/${q.id}/pdf`}>Download proposal PDF</a>}>
        <p className="text-3xl font-semibold tabular-nums" data-testid="price">{money(q.final_price_cents)}</p>
        <p className="text-sm text-slate-600">{q.term_months}-month agreement. Onboarding is included. {q.valid_until && <>Valid until {q.valid_until}.</>}</p>
        {adjusted && <p className="mt-2 rounded bg-amber-50 px-3 py-2 text-sm text-amber-900">Adjusted from the computed {money(q.computed_price_cents)}: {q.adjustment_reason}</p>}
        {q.decision_note && <p className="mt-2 text-sm text-slate-600">Note: {q.decision_note}</p>}
        {q.sent_to && <p className="mt-2 text-sm text-slate-600">Emailed to {q.sent_to}.</p>}
        {q.resulting_agreement_id && <p className="mt-2 text-sm text-green-800">Agreement created. See <Link className="underline" to="/billing/agreements">Billing &gt; Agreements</Link>.</p>}
      </Card>
      <Card title="How the price is built">
        <table className="w-full text-sm">
          <tbody>
            {q.snapshot.base_lines.map((l) => (
              <tr key={l.description} className="border-b border-slate-100"><td className="py-1">{l.description}</td><td className="text-right text-slate-500">{l.quantity} × {money(l.unit_cents)}</td><td className="w-28 text-right tabular-nums">{money(l.amount_cents)}</td></tr>
            ))}
            <tr><td className="py-1 font-medium" colSpan={2}>Base</td><td className="text-right font-medium tabular-nums">{money(q.base_cents)}</td></tr>
          </tbody>
        </table>
        <ul className="mt-3 space-y-1 text-sm">
          {q.snapshot.factors.map((f) => (
            <li key={f.key} className={f.applies ? "" : "text-slate-400"}>
              <b>{f.applies ? `+${percent(f.bp)}` : "no uplift"}</b> {f.label}: {f.reason}
            </li>
          ))}
        </ul>
        <p className="mt-2 text-sm text-slate-600">Total uplift {percent(q.uplift_bp)} (uplifts add). Computed price {money(q.computed_price_cents)}.</p>
        <p className="mt-1 text-sm"><Link className="text-blue-700 hover:underline" to={`/quotes/surveys/${q.survey_id}`}>View the survey</Link></p>
      </Card>
      {editable && write && (
        <Card title="Adjust the price">
          <div className="grid gap-3 sm:grid-cols-[10rem_1fr_auto] sm:items-end">
            <Field label="New monthly price ($)"><input aria-label="New monthly price" className={inputCls} value={price} onChange={(e) => setPrice(e.target.value)} placeholder={(q.final_price_cents / 100).toFixed(2)} /></Field>
            <Field label="Reason (required, internal only)"><input className={inputCls} value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
            <Button variant="secondary" onClick={adjust} disabled={!price}>Apply</Button>
          </div>
          <p className="mt-2 text-xs text-slate-500">A changed price must be approved by an admin before it can be sent. Any edit cancels an earlier approval.</p>
        </Card>
      )}
      <ErrorMsg error={act.error} />
      <Card title="Next step">
        <div className="space-y-3">
          {q.status === "draft" && write && <Button onClick={() => act.mutate({ path: "/submit" })}>{adjusted ? "Submit for approval" : "Approve for sending"}</Button>}
          {q.status === "needs_approval" && (
            <div className="space-y-2">
              <p className="text-sm">Waiting for an admin to approve the changed price.</p>
              {manage && (
                <div className="flex flex-wrap items-end gap-2">
                  <Button onClick={() => act.mutate({ path: "/approve" })}>Approve</Button>
                  <input aria-label="Rejection note" className={inputCls + " max-w-xs"} placeholder="Why not?" value={note} onChange={(e) => setNote(e.target.value)} />
                  <Button variant="secondary" disabled={!note} onClick={() => act.mutate({ path: "/reject", json: { note } })}>Send back</Button>
                </div>
              )}
            </div>
          )}
          {q.status === "approved" && write && (
            <div className="space-y-2">
              <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={email} onChange={(e) => setEmail(e.target.checked)} />Email the PDF to the client now</label>
              {email && <Field label="Send to (blank = the client's primary contact)"><input className={inputCls} value={to} onChange={(e) => setTo(e.target.value)} placeholder="name@client.com" /></Field>}
              <Button onClick={() => act.mutate({ path: "/send", json: { send_email: email, to_emails: to.trim() ? to.split(/[,\s]+/).filter(Boolean) : null } })}>{email ? "Send and lock" : "Mark as sent and lock"}</Button>
              <p className="text-xs text-slate-500">Once sent, the quote can't be changed; revise it to issue a new version.</p>
            </div>
          )}
          {q.status === "sent" && (
            <div className="space-y-3">
              <p className="text-sm">Sent. Record the client's answer when you have it.</p>
              {manage && (
                <div className="flex flex-wrap items-end gap-2">
                  {q.kind === "new" && <Field label="Contract starts"><input aria-label="Contract starts" className={inputCls} type="date" value={start} onChange={(e) => setStart(e.target.value)} /></Field>}
                  <Button onClick={() => act.mutate({ path: "/accept", json: { start_date: start || null } })}>Client accepted</Button>
                  <Button variant="danger" onClick={() => act.mutate({ path: "/decline", json: { note: note || null } })}>Client declined</Button>
                </div>
              )}
            </div>
          )}
          {write && ["sent", "declined", "draft", "needs_approval", "approved"].includes(q.status) && (
            <div className="flex flex-wrap gap-2 border-t border-slate-100 pt-3">
              <Button variant="secondary" onClick={() => act.mutate({ path: "/revise" })}>Revise at today's rates</Button>
              {q.status !== "declined" && <Button variant="danger" onClick={() => { if (window.confirm("Cancel this quote?")) act.mutate({ path: "/cancel", json: {} }); }}>Cancel quote</Button>}
            </div>
          )}
          {["accepted", "cancelled"].includes(q.status) && <p className="text-sm text-slate-500">This quote is closed.</p>}
        </div>
      </Card>
    </div>
  );
}
