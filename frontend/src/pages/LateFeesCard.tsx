import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { AppSettings, api } from "../api";
import { money, parseMoney, parsePercent, percent } from "../money";
import { Button, Card, ErrorMsg, Field, inputCls } from "../ui";

export default function LateFeesCard() {
  const qc = useQueryClient();
  const settings = useQuery({ queryKey: ["lookup", "settings"], queryFn: () => api<AppSettings>("/settings") });
  const s = settings.data;
  const [pct, setPct] = useState<string | null>(null);
  const [flat, setFlat] = useState<string | null>(null);
  const [grace, setGrace] = useState<string | null>(null);
  const [cap, setCap] = useState<string | null>(null);
  const save = useMutation({
    mutationFn: () => {
      const json: Partial<AppSettings> = {};
      if (pct !== null) {
        const bp = parsePercent(pct);
        if (bp === null) throw new Error("Percent must look like 1.5");
        json.late_fee_percent_bp = bp;
      }
      if (flat !== null) {
        const c = parseMoney(flat);
        if (c === null || c < 0) throw new Error("Enter a valid flat fee");
        json.late_fee_flat_cents = c;
      }
      if (grace !== null) json.late_fee_grace_days = Number(grace);
      if (cap !== null) json.late_fee_max_per_invoice = Number(cap);
      return api("/settings", { method: "PATCH", json });
    },
    onSuccess: () => { setPct(null); setFlat(null); setGrace(null); setCap(null); qc.invalidateQueries({ queryKey: ["lookup"] }); },
  });
  if (!s) return null;
  const dirty = pct !== null || flat !== null || grace !== null || cap !== null;
  return (
    <Card title="Late fees">
      <p className="mb-2 text-sm text-slate-600">
        Nothing is charged by itself. Turn late fees on per client (client page → Billing), then review and approve fees on Billing → Late fees.
        An approved fee is added as a charge on the client&apos;s next invoice. Fees never compound: earlier late-fee lines are left out of the amount a new fee is based on.
      </p>
      <div className="grid gap-3 sm:grid-cols-4">
        <Field label="Percent of balance (%)"><input className={inputCls} value={pct ?? percent(s.late_fee_percent_bp).replace("%", "")} onChange={(e) => setPct(e.target.value)} /></Field>
        <Field label="Flat fee ($)"><input className={inputCls} value={flat ?? money(s.late_fee_flat_cents).replace("$", "")} onChange={(e) => setFlat(e.target.value)} /></Field>
        <Field label="Grace days after due date"><input className={inputCls} type="number" min={0} max={365} value={grace ?? s.late_fee_grace_days} onChange={(e) => setGrace(e.target.value)} /></Field>
        <Field label="Most fees per invoice"><input className={inputCls} type="number" min={1} max={12} value={cap ?? s.late_fee_max_per_invoice} onChange={(e) => setCap(e.target.value)} /></Field>
      </div>
      <ErrorMsg error={save.error} />
      {dirty && <div className="mt-2"><Button onClick={() => save.mutate()}>Save</Button></div>}
    </Card>
  );
}
