import { NavLink, Outlet } from "react-router-dom";

export default function BillingLayout() {
  const tab = ({ isActive }: { isActive: boolean }) =>
    `rounded-t px-3 py-1.5 text-sm ${isActive ? "border-b-2 border-blue-600 font-medium" : "text-slate-600 hover:bg-slate-100"}`;
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Billing</h1>
      <nav className="flex gap-1 border-b border-slate-200">
        <NavLink to="/billing/runs" className={tab}>Monthly runs</NavLink>
        <NavLink to="/billing/invoices" className={tab}>Invoices</NavLink>
        <NavLink to="/billing/agreements" className={tab}>Agreements</NavLink>
        <NavLink to="/billing/products" className={tab}>Products</NavLink>
        <NavLink to="/billing/rates" className={tab}>Rates</NavLink>
      </nav>
      <Outlet />
    </div>
  );
}
