import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { AppSettings, api } from "../../../api";
import LateFeesCard from "../../LateFeesCard";
import RemindersCard from "../../RemindersCard";
import { Button, Card, ErrorMsg, Field, inputCls } from "../../../ui";
import { SimpleList } from "./TicketSettings";

export default function BillingSettings() {
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold tracking-tight">Billing</h1>
      <RemindersCard />
      <LateFeesCard />
      <SimpleList title="Internal time categories" path="time-categories" />
      <MileageCard />
      <SimpleList title="Expense categories" path="expense-categories" />
    </div>
  );
}

function MileageCard() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["lookup", "settings"], queryFn: () => api<AppSettings>("/settings") });
  const [text, setText] = useState<string | null>(null);
  const save = useMutation({
    mutationFn: (cents: number) => api("/settings", { method: "PATCH", json: { mileage_rate_cents: cents } }),
    onSuccess: () => { setText(null); qc.invalidateQueries(); },
  });
  if (!q.data) return null;
  const shown = text ?? String(q.data.mileage_rate_cents);
  const cents = /^\d{1,4}$/.test(shown) ? Number(shown) : null;
  return (
    <Card title="Mileage rate">
      <p className="mb-2 text-sm text-slate-600">Cents per mile, whole cents (for example 67 = $0.67). Each trip copies the rate when it is entered, so changing it never rewrites old trips. At 0, mileage cannot be entered.</p>
      <div className="flex items-end gap-2">
        <div className="w-32"><Field label="Cents per mile"><input className={inputCls} inputMode="numeric" value={shown} onChange={(e) => setText(e.target.value)} /></Field></div>
        {text !== null && <Button disabled={cents === null || save.isPending} onClick={() => cents !== null && save.mutate(cents)}>Save</Button>}
      </div>
      <ErrorMsg error={save.error} />
    </Card>
  );
}
