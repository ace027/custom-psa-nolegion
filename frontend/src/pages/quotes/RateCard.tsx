import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { QuoteSettings, api } from "../../api";
import { can, useMe } from "../../auth";
import { money, parseMoney, parsePercent, percent } from "../../money";
import { Button, ErrorMsg, Field, inputCls } from "../../ui";

const RATES: [keyof QuoteSettings, string][] = [
  ["per_user_rate_cents", "Per user"],
  ["workstation_rate_cents", "Per workstation"],
  ["server_rate_cents", "Per server"],
  ["network_rate_cents", "Per network device"],
  ["other_rate_cents", "Per other device"],
];
const UPLIFTS: [keyof QuoteSettings, string, string][] = [
  ["hardware_uplift_bp", "Hardware", "Added when MORE than half of the priced devices are out of warranty"],
  ["server_uplift_bp", "Server", "Added when any priced server is out of warranty"],
  ["legacy_app_uplift_bp", "Legacy application", "Added when the survey lists a legacy line-of-business app"],
];

export default function RateCard() {
  const { data: me } = useMe();
  const canEdit = can(me, "quote:manage");
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["quote-settings"], queryFn: () => api<QuoteSettings>("/quotes/settings") });
  const [f, setF] = useState<Record<string, string>>({});
  useEffect(() => {
    const s = q.data;
    if (!s) return;
    const next: Record<string, string> = { term_months: String(s.term_months), valid_days: String(s.valid_days), intro_text: s.intro_text ?? "" };
    RATES.forEach(([k]) => (next[k] = (Number(s[k]) / 100).toFixed(2)));
    UPLIFTS.forEach(([k]) => (next[k] = percent(Number(s[k])).replace("%", "")));
    setF(next);
  }, [q.data]);
  const save = useMutation({
    mutationFn: () => {
      const body: Record<string, unknown> = { term_months: Number(f.term_months), valid_days: Number(f.valid_days), intro_text: f.intro_text || null };
      for (const [k, label] of RATES) {
        const c = parseMoney(f[k]);
        if (c === null) throw new Error(`${label}: enter an amount like 12.00`);
        body[k] = c;
      }
      for (const [k, label] of UPLIFTS) {
        const bp = parsePercent(f[k]);
        if (bp === null) throw new Error(`${label}: enter a percentage like 25`);
        body[k] = bp;
      }
      return api("/quotes/settings", { method: "PATCH", json: body });
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["quote-settings"] }),
  });
  const set = (k: string) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
  if (!q.data) return <ErrorMsg error={q.error} />;
  return (
    <div className="max-w-2xl space-y-4">
      <p><Link className="text-sm text-blue-700 hover:underline" to="/quotes">← Quotes</Link></p>
      <h1 className="text-xl font-semibold">Quote rate card</h1>
      <p className="text-sm text-slate-600">
        Monthly flat fee = base × (1 + uplifts). The uplifts <b>add</b> (25% + 15% = +40%), never compound. A rate of $0 means that line is not used. Quotes keep the rates they were built with; changing these affects new quotes only.
      </p>
      <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
        <fieldset disabled={!canEdit} className="space-y-3 rounded-lg border border-slate-200 bg-white p-4">
          <legend className="px-1 font-semibold">Monthly base rates ($)</legend>
          <div className="grid gap-3 sm:grid-cols-3">
            {RATES.map(([k, label]) => <Field key={k} label={label}><input className={inputCls} value={f[k] ?? ""} onChange={set(k)} /></Field>)}
          </div>
        </fieldset>
        <fieldset disabled={!canEdit} className="space-y-3 rounded-lg border border-slate-200 bg-white p-4">
          <legend className="px-1 font-semibold">Difficulty uplifts (%)</legend>
          {UPLIFTS.map(([k, label, help]) => (
            <div key={k} className="grid items-end gap-3 sm:grid-cols-[10rem_1fr]">
              <Field label={label}><input aria-label={`${label} uplift`} className={inputCls} value={f[k] ?? ""} onChange={set(k)} /></Field>
              <p className="pb-2 text-sm text-slate-500">{help}</p>
            </div>
          ))}
        </fieldset>
        <fieldset disabled={!canEdit} className="space-y-3 rounded-lg border border-slate-200 bg-white p-4">
          <legend className="px-1 font-semibold">Terms</legend>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Contract term (months)"><input className={inputCls} type="number" min={1} value={f.term_months ?? ""} onChange={set("term_months")} /></Field>
            <Field label="Quote valid for (days)"><input className={inputCls} type="number" min={1} value={f.valid_days ?? ""} onChange={set("valid_days")} /></Field>
          </div>
          <Field label="Introduction on the proposal (optional)"><textarea className={inputCls} rows={3} value={f.intro_text ?? ""} onChange={set("intro_text")} /></Field>
        </fieldset>
        <ErrorMsg error={save.error} />
        {canEdit ? <Button type="submit" disabled={save.isPending}>Save rate card</Button> : <p className="text-sm text-slate-500">Only an admin can change the rate card. Current per-user rate: {money(q.data.per_user_rate_cents)}.</p>}
        {save.isSuccess && <p role="status" className="text-sm text-green-700">Saved.</p>}
      </form>
    </div>
  );
}
