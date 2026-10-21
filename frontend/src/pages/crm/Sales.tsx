import { NavLink, Outlet } from "react-router-dom";

export default function Sales() {
  const tab = ({ isActive }: { isActive: boolean }) =>
    `rounded-t px-3 py-1.5 text-sm ${isActive ? "border-b-2 border-blue-600 font-medium" : "text-slate-600 hover:bg-slate-100"}`;
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold tracking-tight">Sales</h1>
      <nav aria-label="Sales sections" className="flex gap-1 border-b border-slate-200">
        <NavLink to="/crm/pipeline" className={tab}>Pipeline</NavLink>
        <NavLink to="/crm/leads" className={tab}>Leads</NavLink>
        <NavLink to="/crm/forecast" className={tab}>Forecast</NavLink>
        <NavLink to="/crm/renewals" className={tab}>Renewals</NavLink>
      </nav>
      <Outlet />
    </div>
  );
}
