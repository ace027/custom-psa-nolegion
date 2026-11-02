import { NavLink, Navigate, Outlet, useLocation } from "react-router-dom";
import { can, useMe } from "../../auth";
import { usePendingNotices } from "./Reminders";
import { useReceivables } from "./Receivables";

const CATALOG_TABS = ["agreements", "products", "rates", "reports"];

export default function BillingLayout() {
  const { data: me } = useMe();
  const invoices = can(me, "invoice:read");
  const { pathname } = useLocation();
  const rec = useReceivables(invoices);
  const pending = usePendingNotices(invoices).data?.total ?? 0;
  const overdue = rec.data?.totals.overdue_invoice_count ?? 0;
  const tab = ({ isActive }: { isActive: boolean }) =>
    `rounded-t px-3 py-1.5 text-sm ${isActive ? "border-b-2 border-blue-600 font-medium" : "text-slate-600 hover:bg-slate-100"}`;
  // Catalog-only users (billing:read without invoice:read) land on Agreements; the API refuses
  // invoice data to them anyway.
  if (me && !invoices && !CATALOG_TABS.some((t) => pathname.startsWith(`/billing/${t}`)))
    return <Navigate to="/billing/agreements" replace />;
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold tracking-tight">Billing</h1>
      <nav className="flex gap-1 border-b border-slate-200">
        {invoices && (
          <>
          <NavLink to="/billing/runs" className={tab}>Monthly runs</NavLink>
          <NavLink to="/billing/invoices" className={tab}>Invoices</NavLink>
          <NavLink to="/billing/receivables" className={tab}>Receivables{overdue > 0 && <span className="ml-1 rounded bg-red-100 px-1.5 text-xs text-red-800">{overdue} overdue</span>}</NavLink>
          <NavLink to="/billing/reminders" className={tab}>Client emails{pending > 0 && <span className="ml-1 rounded bg-amber-100 px-1.5 text-xs text-amber-900">{pending} to review</span>}</NavLink>
          <NavLink to="/billing/payments" className={tab}>Payments</NavLink>
          <NavLink to="/billing/credit-memos" className={tab}>Credit memos</NavLink>
          <NavLink to="/billing/late-fees" className={tab}>Late fees</NavLink>
          </>
        )}
        <NavLink to="/billing/agreements" className={tab}>Agreements</NavLink>
        <NavLink to="/billing/products" className={tab}>Products</NavLink>
        <NavLink to="/billing/rates" className={tab}>Rates</NavLink>
        {can(me, "report:read") && <NavLink to="/billing/reports" className={tab}>Reports</NavLink>}
      </nav>
      <Outlet />
    </div>
  );
}
