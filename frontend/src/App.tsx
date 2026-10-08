import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, NavLink, Navigate, Outlet, Route, Routes, useLocation, useNavigate } from "react-router-dom";
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
import CsatPage from "./portal/CsatPage";
import PortalApp from "./portal/PortalApp";
import QuotePage from "./pages/quotes/QuotePage";
import QuotesList from "./pages/quotes/QuotesList";
import RateCard from "./pages/quotes/RateCard";
import SurveyPage from "./pages/quotes/SurveyPage";
import Profile from "./pages/Profile";
import Reminders from "./pages/billing/Reminders";
import Reports from "./pages/billing/Reports";
import { RunList, RunPage } from "./pages/billing/Runs";
import Dashboard from "./pages/Dashboard";
import Integrations from "./pages/Integrations";
import WarrantyReport from "./pages/WarrantyReport";
import Login from "./pages/Login";
import OrganizationDetail from "./pages/OrganizationDetail";
import Organizations from "./pages/Organizations";
import Settings from "./pages/Settings";
import Timesheet from "./pages/Timesheet";
import TimerBar from "./pages/TimerBar";
import TicketDetail from "./pages/TicketDetail";
import Search from "./pages/Search";
import Tickets from "./pages/Tickets";
import Users from "./pages/Users";
import { ThemeToggle } from "./ui";

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
  const [open, setOpen] = useState(false);
  const nav = useNavigate();
  const link = ({ isActive }: { isActive: boolean }) =>
    `block rounded-lg px-3 py-2 text-sm ${isActive ? "bg-blue-50 font-semibold text-blue-700" : "text-slate-500 hover:bg-slate-100"}`;
  const close = () => setOpen(false);
  return (
    <div className="min-h-screen md:flex">
      <div className="flex items-center justify-between border-b border-slate-200 bg-surface px-4 py-3 md:hidden">
        <span className="flex items-center gap-2 font-bold">
          <span aria-hidden className="grid h-7 w-7 place-items-center rounded-lg bg-blue-600 text-sm text-on-accent">P</span>PSA
        </span>
        <button type="button" aria-expanded={open} aria-controls="sidebar" className="rounded-lg border border-slate-300 px-3 py-1 text-sm" onClick={() => setOpen(!open)}>Menu</button>
      </div>
      <aside id="sidebar" className={`${open ? "block" : "hidden"} border-b border-slate-200 bg-surface p-3 md:sticky md:top-0 md:block md:h-screen md:w-56 md:shrink-0 md:overflow-y-auto md:border-b-0 md:border-r`}>
        <div className="mb-4 hidden items-center gap-2 px-3 pt-2 font-bold md:flex">
          <span aria-hidden className="grid h-7 w-7 place-items-center rounded-lg bg-blue-600 text-sm text-on-accent">P</span>PSA
        </div>
        <form
          role="search"
          className="mb-3"
          onSubmit={(e) => {
            e.preventDefault();
            const q = String(new FormData(e.currentTarget).get("q") ?? "").trim();
            if (q) {
              nav(`/search?q=${encodeURIComponent(q)}`);
              close();
            }
          }}
        >
          <input name="q" type="search" aria-label="Search" placeholder="Search…" className="w-full rounded-lg border border-slate-300 bg-surface px-3 py-1.5 text-sm" />
        </form>
        <nav className="space-y-0.5" onClick={close}>
          <NavLink to="/dashboard" className={link}>Dashboard</NavLink>
          <NavLink to="/tickets" className={link}>Tickets</NavLink>
          <NavLink to="/organizations" className={link}>Organizations</NavLink>
          {can(me, "time:write") && <NavLink to="/timesheet" className={link}>My timesheet</NavLink>}
          {can(me, "billing:read") && <NavLink to="/billing" className={link}>Billing</NavLink>}
          {can(me, "quote:read") && <NavLink to="/quotes" className={link}>Quotes</NavLink>}
          {can(me, "report:read") && <NavLink to="/warranty" className={link}>Warranty</NavLink>}
          <NavLink to="/users" className={link}>Users</NavLink>
          {can(me, "integration:manage") && <NavLink to="/integrations" className={link}>Integrations</NavLink>}
          {can(me, "config:manage") && <NavLink to="/settings" className={link}>Settings</NavLink>}
          {can(me, "audit:read") && <NavLink to="/audit" className={link}>Audit log</NavLink>}
        </nav>
        <div className="mt-6 space-y-2 border-t border-slate-200 px-3 pt-4 text-sm">
          <Link className="block hover:underline" to="/profile" title="Your notification settings" onClick={close}>{me?.display_name} <span className="text-slate-500">({me?.role})</span></Link>
          <div className="flex items-center gap-3">
            <button className="text-blue-700 hover:underline" onClick={() => logout.mutate()}>Sign out</button>
            <ThemeToggle />
          </div>
        </div>
      </aside>
      <main className="min-w-0 flex-1 p-4 md:p-8">
        <div className="mx-auto max-w-6xl">{can(me, "time:write") && <TimerBar />}<Outlet /></div>
      </main>
    </div>
  );
}

export default function App() {
  // The client portal has its own sign-in and shell; it never touches the staff session.
  const path = useLocation().pathname;
  if (path === "/csat") return <CsatPage />; // public, opened from an emailed link
  if (path.startsWith("/portal")) return <PortalApp />;
  return <StaffApp />;
}

function StaffApp() {
  const { data: me, isLoading, error } = useMe();
  if (isLoading) return <p className="p-6">Loading…</p>;
  if (error) return <p className="p-6 text-red-700">Cannot reach the API.</p>;
  if (!me) return <Login />;
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/search" element={<Search />} />
        <Route path="/tickets" element={<Tickets />} />
        <Route path="/tickets/:id" element={<TicketDetail />} />
        <Route path="/timesheet" element={can(me, "time:write") ? <Timesheet /> : <Navigate to="/" replace />} />
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
            <Route path="reports" element={can(me, "report:read") ? <Reports /> : <Navigate to="/billing" replace />} />
          </Route>
        )}
        {can(me, "quote:read") && (
          <>
            <Route path="/quotes" element={<QuotesList />} />
            <Route path="/quotes/rates" element={<RateCard />} />
            <Route path="/quotes/surveys/:id" element={<SurveyPage />} />
            <Route path="/quotes/:id" element={<QuotePage />} />
          </>
        )}
        <Route path="/warranty" element={can(me, "report:read") ? <WarrantyReport /> : <Navigate to="/" replace />} />
        <Route path="/integrations" element={can(me, "integration:manage") ? <Integrations /> : <Navigate to="/" replace />} />
        <Route path="/profile" element={<Profile />} />
        <Route path="/users" element={<Users />} />
        <Route path="/audit" element={can(me, "audit:read") ? <Audit /> : <Navigate to="/" replace />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
