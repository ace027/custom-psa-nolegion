import { ReactNode } from "react";
import { ThemeChoice, useTheme } from "./theme";

export const inputCls =
  "w-full rounded-lg border border-slate-300 bg-surface px-2.5 py-1.5 text-sm focus:border-blue-500 focus:outline-none";

export function Button({
  variant = "primary",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "danger" }) {
  const styles = {
    primary: "bg-blue-600 text-on-accent hover:bg-blue-700",
    secondary: "border border-slate-300 bg-surface hover:bg-slate-100",
    danger: "border border-red-300 bg-surface text-red-700 hover:bg-red-50",
  }[variant];
  return (
    <button
      {...props}
      className={`rounded-lg px-3 py-1.5 text-sm font-medium disabled:opacity-50 ${styles} ${props.className ?? ""}`}
    />
  );
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block text-sm">
      <span className="mb-1 block font-medium text-slate-700">{label}</span>
      {children}
    </label>
  );
}

export function ErrorMsg({ error }: { error: unknown }) {
  if (!error) return null;
  return (
    <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
      {error instanceof Error ? error.message : String(error)}
    </p>
  );
}

export function Card({ title, actions, children }: { title: string; actions?: ReactNode; children: ReactNode }) {
  return (
    <section className="rounded-xl border border-slate-200 bg-surface p-5 shadow-card">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="font-semibold text-slate-900">{title}</h2>
        {actions}
      </div>
      {children}
    </section>
  );
}

const SLA_STYLE: Record<string, string> = {
  breached: "bg-red-100 text-red-800",
  at_risk: "bg-amber-100 text-amber-800",
  ok: "bg-green-100 text-green-800",
  paused: "bg-slate-100 text-slate-600",
  done: "bg-slate-100 text-slate-500",
  none: "hidden",
};
const SLA_LABEL: Record<string, string> = {
  breached: "SLA breached",
  at_risk: "SLA at risk",
  ok: "SLA ok",
  paused: "SLA paused",
  done: "",
  none: "",
};

export function SlaBadge({ state }: { state: string }) {
  if (!SLA_LABEL[state]) return null;
  return <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${SLA_STYLE[state]}`}>{SLA_LABEL[state]}</span>;
}

export const fmt = (iso: string | null | undefined) => (iso ? new Date(iso).toLocaleString() : "—");

const WARRANTY_STYLE: Record<string, string> = {
  expired: "bg-red-100 text-red-800",
  expiring_30: "bg-amber-100 text-amber-800",
  expiring_60: "bg-amber-50 text-amber-800",
  expiring_90: "bg-yellow-50 text-yellow-800",
  in_warranty: "bg-green-100 text-green-800",
  unknown: "bg-slate-100 text-slate-600",
};

export function WarrantyBadge({ state, label }: { state: string; label: string }) {
  return <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${WARRANTY_STYLE[state]}`}>{label}</span>;
}

export function StatTile({ value, label, tone = "" }: { value: ReactNode; label: string; tone?: string }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-surface px-4 py-3 shadow-card">
      <div className={`text-2xl font-bold ${tone}`}>{value}</div>
      <div className="text-sm text-slate-500">{label}</div>
    </div>
  );
}

const THEME_NEXT: Record<ThemeChoice, ThemeChoice> = { system: "light", light: "dark", dark: "system" };
const THEME_LABEL: Record<ThemeChoice, string> = { system: "Auto", light: "Light", dark: "Dark" };

// One button cycling Auto (follow the OS) -> Light -> Dark. The choice is remembered in this browser.
export function ThemeToggle({ className = "" }: { className?: string }) {
  const { choice, set } = useTheme();
  return (
    <button
      type="button"
      onClick={() => set(THEME_NEXT[choice])}
      title="Colour theme: click to change"
      aria-label={`Theme: ${THEME_LABEL[choice]}. Click to change.`}
      className={`rounded-lg border border-slate-300 px-2.5 py-1 text-xs font-medium text-slate-600 hover:bg-slate-100 ${className}`}
    >
      {choice === "dark" ? "☾" : choice === "light" ? "☀" : "◐"} {THEME_LABEL[choice]}
    </button>
  );
}
