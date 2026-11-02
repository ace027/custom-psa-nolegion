import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Suspense, lazy, useCallback, useEffect, useRef, useState } from "react";
import { Navigate, Outlet, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { api } from "./api";
import { can, useMe } from "./auth";
import ErrorBoundary from "./components/ErrorBoundary";
import Audit from "./pages/Audit";
import Agreements from "./pages/billing/Agreements";
import BillingLayout from "./pages/billing/BillingLayout";
import { InvoiceList, InvoicePage } from "./pages/billing/Invoices";
import CreditMemos from "./pages/billing/CreditMemos";
import LateFees from "./pages/billing/LateFees";
import Payments from "./pages/billing/Payments";
import Products from "./pages/billing/Products";
import Rates from "./pages/billing/Rates";
import Receivables from "./pages/billing/Receivables";
import AgingReport from "./pages/reports/AgingReport";
import ProfitabilityReport from "./pages/reports/ProfitabilityReport";
import ReportSchedules from "./pages/reports/ReportSchedules";
import SlaReport from "./pages/reports/SlaReport";
import UtilisationReport from "./pages/reports/UtilisationReport";
import Forecast from "./pages/crm/Forecast";
import Leads from "./pages/crm/Leads";
import OpportunityPage from "./pages/crm/OpportunityPage";
import Pipeline from "./pages/crm/Pipeline";
import Inventory from "./pages/procurement/Inventory";
import MarkupRules from "./pages/procurement/MarkupRules";
import PurchaseOrderPage from "./pages/procurement/PurchaseOrderPage";
import PurchaseOrders from "./pages/procurement/PurchaseOrders";
import Renewals from "./pages/crm/Renewals";
import Sales from "./pages/crm/Sales";
import CsatPage from "./portal/CsatPage";
import PortalApp from "./portal/PortalApp";
import QuotePage from "./pages/quotes/QuotePage";
import QuotesList from "./pages/quotes/QuotesList";
import RateCard from "./pages/quotes/RateCard";
import SurveyPage from "./pages/quotes/SurveyPage";
import ProjectDetail from "./pages/ProjectDetail";
import Projects from "./pages/Projects";
import Profile from "./pages/Profile";
import Reminders from "./pages/billing/Reminders";
import Reports from "./pages/billing/Reports";
import { RunList, RunPage } from "./pages/billing/Runs";
import Dashboard from "./pages/Dashboard";
import ApiKeys from "./pages/ApiKeys";
import Automation from "./pages/Automation";
import Webhooks from "./pages/Webhooks";
import Integrations from "./pages/Integrations";
import WarrantyReport from "./pages/WarrantyReport";
import OnCall from "./pages/OnCall";
import OnCallWidget from "./OnCallWidget";
import Login from "./pages/Login";
import OrganizationDetail from "./pages/OrganizationDetail";
import Organizations from "./pages/Organizations";
import Settings, { SettingsLayout } from "./pages/Settings";
import GeneralSettings from "./pages/admin/settings/GeneralSettings";
import MailCalendarSettings from "./pages/admin/settings/MailCalendarSettings";
import TicketSettings from "./pages/admin/settings/TicketSettings";
import BillingSettings from "./pages/admin/settings/BillingSettings";
import PortalSettings from "./pages/admin/settings/PortalSettings";
import SalesSettings from "./pages/admin/settings/SalesSettings";
import SchedulingSettings from "./pages/admin/settings/SchedulingSettings";
import Expenses from "./pages/Expenses";
import Timesheet from "./pages/Timesheet";
import TimerBar from "./pages/TimerBar";
import TicketDetail from "./pages/TicketDetail";
import Search from "./pages/Search";
import Tickets from "./pages/Tickets";
import Users from "./pages/Users";
import AdminLayout from "./nav/AdminLayout";
import AllPages from "./nav/AllPages";
import { NAV_SECTIONS, canOpen, itemForPath, visibleItems } from "./nav/navConfig";
import Rail, { Icon } from "./nav/Rail";
import { useBookmarks } from "./nav/useBookmarks";

// The dispatch board pulls in react-big-calendar, so it is split into its own chunk.
const Dispatch = lazy(() => import("./pages/Dispatch"));

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
  const nav = useNavigate();
  const { pathname } = useLocation();
  const bookmarks = useBookmarks(me);
  const [allOpen, setAllOpen] = useState(false);
  const allButton = useRef<HTMLButtonElement>(null);
  const search = useRef<HTMLInputElement>(null);
  const closeAll = useCallback(() => setAllOpen(false), []);
  useEffect(closeAll, [pathname, closeAll]); // any navigation closes the panel
  const page = itemForPath(pathname);
  const current = page && canOpen(me, page) ? page : undefined;
  const section = NAV_SECTIONS.find((s) => s.id === current?.section);
  if (!me) return null;
  return (
    <div className="min-h-screen md:flex">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-2 focus:top-2 focus:z-50 focus:rounded-lg focus:bg-blue-600 focus:px-3 focus:py-1.5 focus:text-on-accent">
        Skip to content
      </a>
      <Rail
        me={me}
        bookmarks={bookmarks}
        allOpen={allOpen}
        onToggleAll={() => setAllOpen((o) => !o)}
        allButtonRef={allButton}
        onGoTo={() => search.current?.focus()}
      />
      {allOpen && <AllPages me={me} bookmarks={bookmarks} onClose={closeAll} returnFocus={allButton} />}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex flex-wrap items-center gap-3 border-b border-slate-200 bg-slate-50 px-4 py-2 md:px-8">
          {current && (
            <>
              <span className="text-sm text-slate-500">
                <span className="hidden sm:inline">{section?.label} › </span>
                <b className="font-semibold text-slate-900">{current.label}</b>
              </span>
              <button
                type="button"
                aria-pressed={bookmarks.isBookmarked(current.id)}
                onClick={() => bookmarks.toggle(current.id)}
                className={`inline-flex items-center gap-1 rounded-lg border bg-surface px-2 py-0.5 text-xs ${bookmarks.isBookmarked(current.id) ? "border-amber-700 text-amber-700" : "border-slate-300 text-slate-600 hover:bg-slate-100"}`}
              >
                <Icon name="star" className="h-3.5 w-3.5" filled={bookmarks.isBookmarked(current.id)} />
                Bookmark this page
              </button>
            </>
          )}
          <form
            role="search"
            className="ml-auto w-full max-w-xs flex-1 sm:w-auto"
            onSubmit={(e) => {
              e.preventDefault();
              const q = String(new FormData(e.currentTarget).get("q") ?? "").trim();
              if (q) nav(`/search?q=${encodeURIComponent(q)}`);
            }}
          >
            <input ref={search} name="q" type="search" aria-label="Search" placeholder="Search…" className="w-full rounded-lg border border-slate-300 bg-surface px-3 py-1.5 text-sm" />
          </form>
          <div className="[&>section]:mt-0 [&>section]:py-1">
            <OnCallWidget />
          </div>
          <button type="button" className="text-sm text-blue-700 hover:underline" onClick={() => logout.mutate()}>Sign out</button>
        </header>
        <main id="main" tabIndex={-1} className="min-w-0 flex-1 p-4 pb-24 focus:outline-none md:p-8">
          <div className="mx-auto max-w-6xl">
            {bookmarks.error && <p role="alert" className="mb-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{bookmarks.error}</p>}
            {can(me, "time:write") && <TimerBar />}
            <ErrorBoundary><Outlet /></ErrorBoundary>
          </div>
        </main>
      </div>
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
        {can(me, "ticket:read") && (
          <>
            <Route path="/projects" element={<Projects />} />
            <Route path="/projects/:id" element={<ProjectDetail />} />
          </>
        )}
        <Route
          path="/dispatch"
          element={can(me, "schedule:read") ? <Suspense fallback={<p>Loading…</p>}><Dispatch /></Suspense> : <Navigate to="/" replace />}
        />
        <Route path="/oncall" element={can(me, "schedule:read") ? <OnCall /> : <Navigate to="/" replace />} />
        <Route path="/timesheet" element={can(me, "time:write") ? <Timesheet /> : <Navigate to="/" replace />} />
        <Route path="/expenses" element={can(me, "time:write") ? <Expenses /> : <Navigate to="/" replace />} />
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
            <Route path="credit-memos" element={<CreditMemos />} />
            <Route path="late-fees" element={<LateFees />} />
            <Route path="agreements" element={<Agreements />} />
            <Route path="products" element={<Products />} />
            <Route path="rates" element={<Rates />} />
            <Route path="reports" element={can(me, "report:read") ? <Reports /> : <Navigate to="/billing" replace />} />
          </Route>
        )}
        {can(me, "crm:read") && (
          <>
            <Route path="/crm" element={<Sales />}>
              <Route index element={<Navigate to="pipeline" replace />} />
              <Route path="pipeline" element={<Pipeline />} />
              <Route path="leads" element={<Leads />} />
              <Route path="forecast" element={<Forecast />} />
              <Route path="renewals" element={<Renewals />} />
            </Route>
            <Route path="/crm/opportunities/:id" element={<OpportunityPage />} />
          </>
        )}
        {can(me, "procurement:read") && (
          <>
            <Route path="/procurement" element={<PurchaseOrders />} />
            <Route path="/procurement/purchase-orders/:id" element={<PurchaseOrderPage />} />
            <Route path="/procurement/inventory" element={<Inventory />} />
            <Route path="/procurement/markup" element={<MarkupRules />} />
          </>
        )}
        {can(me, "quote:read") && (
          <>
            <Route path="/quotes" element={<QuotesList />} />
            <Route path="/quotes/rates" element={<RateCard />} />
            <Route path="/quotes/surveys/:id" element={<SurveyPage />} />
            <Route path="/quotes/:id" element={<QuotePage />} />
          </>
        )}
        {can(me, "report:read") && (
          <>
            <Route path="/reports/sla" element={<SlaReport />} />
            <Route path="/reports/utilisation" element={<UtilisationReport />} />
            <Route path="/reports/aging" element={<AgingReport />} />
            <Route path="/reports/profitability" element={<ProfitabilityReport />} />
            <Route path="/reports/schedules" element={<ReportSchedules />} />
          </>
        )}
        <Route path="/warranty" element={can(me, "report:read") ? <WarrantyReport /> : <Navigate to="/" replace />} />
        <Route path="/api-keys" element={can(me, "apikey:manage") ? <ApiKeys /> : <Navigate to="/" replace />} />
        <Route path="/webhooks" element={can(me, "automation:manage") ? <Webhooks /> : <Navigate to="/" replace />} />
        <Route path="/automation" element={can(me, "automation:manage") ? <Automation /> : <Navigate to="/" replace />} />
        <Route path="/integrations" element={can(me, "integration:manage") ? <Integrations /> : <Navigate to="/" replace />} />
        <Route path="/profile" element={<Profile />} />
        <Route path="/admin" element={<AdminLayout />}>
          <Route index element={<Navigate to={visibleItems(me).find((i) => i.section === "admin")?.route ?? "/"} replace />} />
          {/* Users stays readable by every role (user:read); only the nav lists it for user:manage. */}
          <Route path="users" element={<Users />} />
          <Route
            path="settings"
            element={can(me, "config:manage") || can(me, "service:configure") ? <SettingsLayout /> : <Navigate to="/" replace />}
          >
            <Route index element={<Settings />} />
            {([
              ["tickets", "service:configure", <TicketSettings />],
              ["scheduling", "service:configure", <SchedulingSettings />],
              ["mail", "config:manage", <MailCalendarSettings />],
              ["billing", "config:manage", <BillingSettings />],
              ["portal", "config:manage", <PortalSettings />],
              ["sales", "config:manage", <SalesSettings />],
              ["general", "config:manage", <GeneralSettings />],
            ] as const).map(([path, perm, page]) => (
              <Route key={path} path={path} element={can(me, perm) ? page : <Navigate to="/admin/settings" replace />} />
            ))}
          </Route>
        </Route>
        {/* Moved and removed pages */}
        <Route path="/settings" element={<Navigate to="/admin/settings" replace />} />
        <Route path="/users" element={<Navigate to="/admin/users" replace />} />
        <Route path="/kb/*" element={<Navigate to="/tickets" replace />} />
        <Route path="/audit" element={can(me, "audit:read") ? <Audit /> : <Navigate to="/" replace />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
