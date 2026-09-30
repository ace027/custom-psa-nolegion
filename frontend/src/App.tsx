import { useMutation, useQueryClient } from "@tanstack/react-query";
import { NavLink, Navigate, Outlet, Route, Routes } from "react-router-dom";
import { api } from "./api";
import { can, useMe } from "./auth";
import Audit from "./pages/Audit";
import Agreements from "./pages/billing/Agreements";
import BillingLayout from "./pages/billing/BillingLayout";
import { InvoiceList, InvoicePage } from "./pages/billing/Invoices";
import Payments from "./pages/billing/Payments";
import Products from "./pages/billing/Products";
import Rates from "./pages/billing/Rates";
import Receivables from "./pages/billing/Receivables";
import Reminders from "./pages/billing/Reminders";
import { RunList, RunPage } from "./pages/billing/Runs";
import Dashboard from "./pages/Dashboard";
import Login from "./pages/Login";
import OrganizationDetail from "./pages/OrganizationDetail";
import Organizations from "./pages/Organizations";
import Settings from "./pages/Settings";
import TicketDetail from "./pages/TicketDetail";
import Tickets from "./pages/Tickets";
import Users from "./pages/Users";

function Layout() {
  const { data: me } = useMe();
  const qc = useQueryClient();
  const logout = useMutation({
    mutationFn: () => api("/auth/logout", { method: "POST" }),
    onSuccess: () => {
      qc.setQueryData(["me"], null); // App swaps to the login page
      qc.removeQueries({ predicate: (q) => q.queryKey[0] !== "me" }); // drop cached client data
    },
  });
  const link = ({ isActive }: { isActive: boolean }) =>
    `rounded px-2 py-1 text-sm ${isActive ? "bg-slate-200 font-medium" : "hover:bg-slate-100"}`;
  return (
    <div className="mx-auto max-w-5xl p-4">
      <header className="mb-6 flex items-center justify-between border-b border-slate-200 pb-3">
        <nav className="flex items-center gap-2">
          <span className="mr-4 font-bold">PSA</span>
          <NavLink to="/dashboard" className={link}>Dashboard</NavLink>
          <NavLink to="/tickets" className={link}>Tickets</NavLink>
          <NavLink to="/organizations" className={link}>Organizations</NavLink>
          {can(me, "billing:read") && <NavLink to="/billing" className={link}>Billing</NavLink>}
          <NavLink to="/users" className={link}>Users</NavLink>
          {can(me, "config:manage") && <NavLink to="/settings" className={link}>Settings</NavLink>}
          {can(me, "audit:read") && <NavLink to="/audit" className={link}>Audit log</NavLink>}
        </nav>
        <div className="flex items-center gap-3 text-sm">
          <span>{me?.display_name} <span className="text-slate-500">({me?.role})</span></span>
          <button className="text-blue-700 hover:underline" onClick={() => logout.mutate()}>Sign out</button>
        </div>
      </header>
      <Outlet />
    </div>
  );
}

export default function App() {
  const { data: me, isLoading, error } = useMe();
  if (isLoading) return <p className="p-6">Loading…</p>;
  if (error) return <p className="p-6 text-red-700">Cannot reach the API.</p>;
  if (!me) return <Login />;
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/tickets" element={<Tickets />} />
        <Route path="/tickets/:id" element={<TicketDetail />} />
        <Route path="/settings" element={can(me, "config:manage") ? <Settings /> : <Navigate to="/" replace />} />
        <Route path="/organizations" element={<Organizations />} />
        <Route path="/organizations/:id" element={<OrganizationDetail />} />
        {can(me, "billing:read") && (
          <Route path="/billing" element={<BillingLayout />}>
            <Route index element={<Navigate to="runs" replace />} />
            <Route path="runs" element={<RunList />} />
            <Route path="runs/:id" element={<RunPage />} />
            <Route path="invoices" element={<InvoiceList />} />
            <Route path="invoices/:id" element={<InvoicePage />} />
            <Route path="receivables" element={<Receivables />} />
            <Route path="reminders" element={<Reminders />} />
            <Route path="payments" element={<Payments />} />
            <Route path="agreements" element={<Agreements />} />
            <Route path="products" element={<Products />} />
            <Route path="rates" element={<Rates />} />
          </Route>
        )}
        <Route path="/users" element={<Users />} />
        <Route path="/audit" element={can(me, "audit:read") ? <Audit /> : <Navigate to="/" replace />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
