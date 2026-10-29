import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";

const json = (body: unknown, status = 200) => () => new Response(JSON.stringify(body), { status });
const me = (role: string, permissions: string[], id = 1) => ({ id, email: "u@example.com", display_name: "Una", role, permissions });
const TECH = ["ticket:read"];
const BILLING = ["ticket:read", "report:read"];
const ADMIN = ["ticket:read", "report:read", "user:manage", "config:manage"];

const board = { my_open: [], unassigned: [], sla_at_risk: [], counts: { open: 3, mine: 1, unassigned: 2, sla_at_risk: 0, needs_triage: 0 } };
const mine = {
  open_tickets: 4, sla_at_risk: 1, sla_breached: 2, appointments_today: 3,
  week: { logged_minutes: 1500, billable_minutes: 1200, capacity_minutes: 2400, utilisation_bp: 6250 },
};
const manager = {
  revenue_mtd_cents: 1234500, margin_mtd_cents: 400000, margin_mtd_bp: 3240, ar_total_cents: 880000,
  ar_buckets: { current_cents: 500000, d1_30_cents: 200000, d31_60_cents: 100000, d61_90_cents: 50000, d90_plus_cents: 30000 },
  unbilled_cents: 77700, sla_30d: { first_response_met_bp: 9250, resolution_met_bp: null, n: 40 }, team_utilisation_last_week_bp: 7500,
};

let calls: string[] = [];
function go(path: string, role: string, perms: string[], h: Record<string, () => Response> = {}) {
  const handlers: Record<string, () => Response> = {
    "/api/auth/me": json(me(role, perms)), "/api/dashboard": json(board), "/api/dashboard/me": json(mine),
    "/api/csat/summary?days=90": json({ days: 90, requested: 0, responses: 0, average: null, distribution: {} }), ...h,
  };
  vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => {
    const key = init?.method && init.method !== "GET" ? `${init.method} ${url}` : url;
    calls.push(`${key} ${init?.body ?? ""}`);
    return Promise.resolve((handlers[key] ?? handlers[key.split("?")[0]])?.() ?? new Response("{}", { status: 404 }));
  }));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><MemoryRouter initialEntries={[path]}><App /></MemoryRouter></QueryClientProvider>);
}
beforeEach(() => { calls = []; });
afterEach(() => vi.unstubAllGlobals());

describe("role dashboards", () => {
  it("shows a technician My week but not Business", async () => {
    go("/dashboard", "tech", TECH);
    expect(await screen.findByRole("heading", { name: "My week" })).toBeInTheDocument();
    expect(await screen.findByText("62.50%")).toBeInTheDocument();
    expect(screen.getByText("25h 00m")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Business" })).not.toBeInTheDocument();
    expect(calls.some((c) => c.startsWith("/api/reports/dashboard"))).toBe(false);
  });

  it("shows a billing user the Business section with percentages and n", async () => {
    go("/dashboard", "billing", BILLING, { "/api/reports/dashboard": json(manager) });
    expect(await screen.findByRole("heading", { name: "Business" })).toBeInTheDocument();
    expect(await screen.findByText("92.50% (n=40)")).toBeInTheDocument();
    expect(screen.getByText("$12,345.00")).toBeInTheDocument();
    expect(screen.getByText("32.40%")).toBeInTheDocument();
    expect(screen.getByText("75.00%")).toBeInTheDocument();
    // a null percentage is a dash, never 0%
    expect(screen.getByText("-")).toBeInTheDocument();
    expect(screen.getByText("SLA first response met, 30 days").closest("a")).toHaveAttribute("href", "/reports/sla");
    expect(screen.getByRole("heading", { name: "My week" })).toBeInTheDocument();
  });

  it("shows the Reports nav group only with report:read", async () => {
    const { unmount } = go("/dashboard", "billing", BILLING, { "/api/reports/dashboard": json(manager) });
    expect(await screen.findByRole("link", { name: "SLA report" })).toBeInTheDocument();
    unmount();
    go("/dashboard", "tech", TECH);
    await screen.findByRole("heading", { name: "My week" });
    expect(screen.queryByRole("link", { name: "SLA report" })).not.toBeInTheDocument();
  });
});

describe("report pages", () => {
  it("renders an SLA row with n and a dash for a null percentage, and a matching CSV link", async () => {
    const clock = (over = {}) => ({ met: 9, breached: 1, pending: 0, no_sla: 0, met_bp: 9000, p50_minutes: 125, p90_minutes: 300, ...over });
    go("/reports/sla", "billing", BILLING, {
      "/api/reports/dashboard": json(manager),
      "/api/reports/sla": json({ range: { start: "2026-10-01", end: "2026-10-29" }, group: "priority", rows: [{ key: 1, label: "High", n: 10, first_response: clock(), resolution: clock({ met: 0, breached: 0, met_bp: null, p50_minutes: null, p90_minutes: null }) }], totals: { n: 10, first_response: clock(), resolution: clock({ met_bp: null }) } }),
    });
    expect(await screen.findByText("High")).toBeInTheDocument();
    expect(screen.getAllByText("90.00% (n=10)").length).toBeGreaterThan(0);
    expect(screen.getAllByText("2h 05m").length).toBeGreaterThan(0);
    expect(screen.getAllByText("-").length).toBeGreaterThan(0);
    const href = screen.getByRole("link", { name: "Download CSV" }).getAttribute("href") ?? "";
    expect(href).toMatch(/^\/api\/reports\/sla\.csv\?from=\d{4}-\d{2}-01&to=\d{4}-\d{2}-\d{2}&group=priority$/);
  });

  it("shows an empty message and the schedule form only with config:manage", async () => {
    go("/reports/schedules", "billing", BILLING, { "/api/reports/schedules": json([]), "/api/users": json([]) });
    expect(await screen.findByText("No scheduled reports yet.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "New schedule" })).not.toBeInTheDocument();
  });
});

describe("cost rate", () => {
  const users = [
    { id: 1, email: "a@example.com", display_name: "Una", role: "admin", is_active: true, last_login_at: null },
    { id: 2, email: "t@example.com", display_name: "Tom", role: "tech", is_active: true, last_login_at: null },
  ];

  it("is absent without user:manage", async () => {
    go("/users", "billing", BILLING, { "/api/users": json(users) });
    expect(await screen.findByText("Tom")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit Tom" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Cost rate (per hour)")).not.toBeInTheDocument();
    expect(calls.some((c) => c.includes("cost-rate"))).toBe(false);
  });

  it("loads and saves cents for an admin", async () => {
    go("/users", "admin", ADMIN, {
      "/api/users": json(users),
      "/api/users/2/cost-rate": json({ user_id: 2, cost_rate_cents: 4500 }),
      "PUT /api/users/2/cost-rate": json({ user_id: 2, cost_rate_cents: 9000 }),
    });
    fireEvent.click(await screen.findByRole("button", { name: "Edit Tom" }));
    const input = await screen.findByDisplayValue("45.00");
    fireEvent.change(input, { target: { value: "90.00" } });
    fireEvent.click(screen.getByRole("button", { name: "Save cost rate" }));
    await waitFor(() => expect(calls.some((c) => c.startsWith("PUT /api/users/2/cost-rate") && c.includes('"cost_rate_cents":9000'))).toBe(true));
  });
});
