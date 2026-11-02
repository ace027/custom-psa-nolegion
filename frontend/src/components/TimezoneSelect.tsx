import { useMemo, useState } from "react";
import { inputCls } from "../ui";

// shortcut: fallback list is short, used only where Intl.supportedValuesOf is missing (old browsers).
const FALLBACK = [
  "UTC", "America/New_York", "America/Chicago", "America/Denver", "America/Los_Angeles", "America/Phoenix", "America/Anchorage",
  "America/Toronto", "America/Sao_Paulo", "Europe/London", "Europe/Paris", "Europe/Berlin", "Africa/Johannesburg",
  "Asia/Dubai", "Asia/Kolkata", "Asia/Singapore", "Asia/Tokyo", "Australia/Sydney", "Pacific/Auckland",
];

function allZones(): string[] {
  const f = (Intl as unknown as { supportedValuesOf?: (k: string) => string[] }).supportedValuesOf;
  try {
    const z = f ? f("timeZone") : [];
    return z.length ? z : FALLBACK;
  } catch {
    return FALLBACK;
  }
}

function offsetLabel(zone: string): string {
  try {
    const p = new Intl.DateTimeFormat("en-US", { timeZone: zone, timeZoneName: "longOffset" }).formatToParts(new Date());
    const v = p.find((x) => x.type === "timeZoneName")?.value ?? "";
    return v === "GMT" ? "UTC+00:00" : v.replace("GMT", "UTC").replace("-", "−");
  } catch {
    return "";
  }
}

export default function TimezoneSelect({ value, onChange, label = "Time zone" }: { value: string; onChange: (zone: string) => void; label?: string }) {
  const [filter, setFilter] = useState("");
  const zones = useMemo(() => allZones().map((z) => ({ z, text: `${z} (${offsetLabel(z)})` })), []);
  const q = filter.trim().toLowerCase();
  const shown = zones.filter((o) => o.z === value || o.text.toLowerCase().includes(q.replace(/ /g, "_")));
  const known = zones.some((o) => o.z === value);
  const groups = new Map<string, typeof zones>();
  for (const o of shown) {
    const region = o.z.includes("/") ? o.z.split("/")[0] : "Other";
    groups.set(region, [...(groups.get(region) ?? []), o]);
  }
  return (
    <div className="block text-sm">
      <span className="mb-1 block font-medium text-slate-700">{label}</span>
      <input className={`${inputCls} mb-1`} type="search" aria-label={`Filter ${label.toLowerCase()}s`} placeholder="Type to filter…" value={filter} onChange={(e) => setFilter(e.target.value)} />
      <select className={inputCls} aria-label={label} value={value} onChange={(e) => onChange(e.target.value)}>
        {!known && <option value={value}>{value}</option>}
        {[...groups].sort(([a], [b]) => a.localeCompare(b)).map(([region, opts]) => (
          <optgroup key={region} label={region}>
            {opts.map((o) => <option key={o.z} value={o.z}>{o.text}</option>)}
          </optgroup>
        ))}
      </select>
    </div>
  );
}
