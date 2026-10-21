import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useState } from "react";
import { Link } from "react-router-dom";
import { crmApi } from "../api";
import { can, useMe } from "../auth";
import { money, parseMoney } from "../money";
import { Button, Card, ErrorMsg, Field, inputCls } from "../ui";

export default function OrgOpportunitiesCard({ orgId }: { orgId: number }) {
  const { data: me } = useMe();
  const write = can(me, "crm:write");
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["crm", "opportunities", "org", orgId], queryFn: () => crmApi.opportunities({ organization_id: orgId }) });
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState("");
  const [monthly, setMonthly] = useState("0.00");
  const [bad, setBad] = useState("");
  const add = useMutation({
    mutationFn: (cents: number) => crmApi.createOpportunity({ organization_id: orgId, name: name.trim(), monthly_cents: cents }),
    onSuccess: () => {
      setAdding(false);
      setName("");
      setMonthly("0.00");
      qc.invalidateQueries({ queryKey: ["crm"] });
    },
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const cents = parseMoney(monthly);
    if (cents === null || cents < 0) return setBad("Enter the monthly amount, for example 1500.00.");
    setBad("");
    add.mutate(cents);
  };
  const rows = q.data ?? [];
  const open = rows.filter((o) => o.stage_kind === "open");
  const closed = rows
    .filter((o) => o.stage_kind !== "open")
    .sort((a, b) => (b.closed_at ?? "").localeCompare(a.closed_at ?? ""))
    .slice(0, 5);
  const list = (items: typeof rows) => (
    <ul className="divide-y divide-slate-100 text-sm">
      {items.map((o) => (
        <li key={o.id} className="flex flex-wrap items-center justify-between gap-2 py-1.5">
          <Link className="text-blue-700 hover:underline" to={`/crm/opportunities/${o.id}`}>{o.name}</Link>
          <span className="text-slate-600">{o.stage_name} · {money(o.monthly_cents)}/mo</span>
        </li>
      ))}
    </ul>
  );
  return (
    <Card title="Opportunities" actions={write ? <Button variant="secondary" onClick={() => setAdding(!adding)}>{adding ? "Close" : "New opportunity"}</Button> : undefined}>
      <ErrorMsg error={q.error} />
      {write && adding && (
        <form onSubmit={submit} className="mb-3 grid gap-3 sm:grid-cols-[1fr_10rem_auto] sm:items-end">
          <Field label="Opportunity name"><input required className={inputCls} value={name} onChange={(e) => setName(e.target.value)} /></Field>
          <Field label="Monthly ($)"><input className={inputCls} value={monthly} onChange={(e) => setMonthly(e.target.value)} inputMode="decimal" /></Field>
          <Button type="submit" disabled={add.isPending || !name.trim()}>Add</Button>
          <div className="sm:col-span-3 space-y-2">
            {bad && <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{bad}</p>}
            <ErrorMsg error={add.error} />
          </div>
        </form>
      )}
      {q.data && rows.length === 0 && <p className="text-sm text-slate-500">No opportunities for this client.</p>}
      {open.length > 0 && <><h3 className="text-sm font-medium text-slate-700">Open</h3>{list(open)}</>}
      {closed.length > 0 && <><h3 className="mt-3 text-sm font-medium text-slate-700">Recently closed</h3>{list(closed)}</>}
    </Card>
  );
}
