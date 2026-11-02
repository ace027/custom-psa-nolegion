import { Link, NavLink, Outlet } from "react-router-dom";
import { useMe } from "../auth";
import { settingsPages } from "../nav/navConfig";

// Existing tests and callers import these two cards from here.
export { AppointmentEmailsCard, OutlookSyncCard } from "./admin/settings/MailCalendarSettings";

/** /admin/settings/*: a sub-nav of the settings pages this person may open, above the page. */
export function SettingsLayout() {
  const { data: me } = useMe();
  const pages = settingsPages(me);
  const link = ({ isActive }: { isActive: boolean }) =>
    `rounded-lg px-3 py-1.5 text-sm ${isActive ? "bg-blue-50 font-semibold text-blue-700" : "text-slate-600 hover:bg-slate-100"}`;
  return (
    <div className="space-y-4">
      <nav aria-label="Settings pages">
        <ul className="flex flex-wrap gap-1">
          {pages.map((p) => (
            <li key={p.id}><NavLink to={`/admin/settings/${p.path}`} className={link}>{p.label}</NavLink></li>
          ))}
        </ul>
      </nav>
      <Outlet />
    </div>
  );
}

/** The Settings landing page: the settings pages this person may open. */
export default function Settings() {
  const { data: me } = useMe();
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold tracking-tight">Settings</h1>
      <ul className="grid gap-3 sm:grid-cols-2">
        {settingsPages(me).map((p) => (
          <li key={p.id} className="rounded-xl border border-slate-200 bg-surface p-4 shadow-card">
            <Link to={`/admin/settings/${p.path}`} className="font-semibold text-blue-700 hover:underline">{p.label}</Link>
            <p className="mt-1 text-sm text-slate-600">{p.about}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}
