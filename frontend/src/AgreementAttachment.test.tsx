import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const ticket = {
  id: 7, number: 10007, organization_id: 1, organization_name: "Acme", contact_id: null, contact_name: null,
  site_id: null, queue_id: 1, queue_name: "Support", category_id: null, category_name: null,
  priority_id: 3, priority_name: "Normal", priority_rank: 3, status: "open", assignee_id: null,
  assignee_name: null, subject: "Printer", description: "", source: "ui", requester_email: null, needs_triage: false,
  sla_state: "ok", sla_first_response_due: null, sla_resolution_due: null, first_responded_at: null,
  created_at: "2026-09-30T12:00:00Z", updated_at: "2026-09-30T12:00:00Z", agreement_id: null,
};
const agr = (id: number, type: string, over = {}) => ({
  id, organization_id: 1, organization_name: "Acme", name: `Plan ${id}`, type, block_minutes: type === "block" ? 600 : null,
  unit_price_cents: 1000, quantity: 1, taxable: false, start_date: "2026-01-01", end_date: null, notes: null,
  monthly_amount_cents: 1000, all_inclusive: false, rollover: "expire", rollover_cap_minutes: null, ...over,
});
const entry = (id: number, over = {}) => ({
  id, user_id: 1, work_type_id: 1, work_date: "2026-10-01", minutes_actual: 30, minutes_billable: 30, billable: true,
  entry_type: "labour", note: null, voided_at: null, agreement_id: null, invoice_line_id: null, ...over,
});

type Req = { path: string; query: string; method?: string; body?: string };
function run(path: string, perms: string[], routes: Record<string, (r: Req) => Response>) {
  const calls: Req[] = [];
  vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => {
    const u = new URL(url, "http://x");
    const r = { path: u.pathname, query: u.search, method: init?.method, body: init?.body as string | undefined };
    calls.push(r);
    const me = { id: 1, email: "u@e.com", display_name: "U", role: "tech", permissions: perms };
    if (r.path === "/api/v1/auth/me") return Promise.resolve(json(me));
    const h = routes[r.path];
    if (h) return Promise.resolve(h(r));
    if (r.path.endsWith("/organizations")) return Promise.resolve(json({ items: [{ id: 1, name: "Acme" }], total: 1 }));
    return Promise.resolve(r.path.endsWith("/notes") || r.path.endsWith("/attachments") || r.path.endsWith("/links") ? json([]) : new Response("{}", { status: 404 }));
  }));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={qc}><MemoryRouter initialEntries={[path]}><App /></MemoryRouter></QueryClientProvider>);
  return calls;
}
afterEach(() => vi.unstubAllGlobals());

const STAFF = ["ticket:read", "ticket:write", "time:write", "billing:read"];
const ticketRoutes = (over: Record<string, (r: Req) => Response> = {}) => ({
  "/api/v1/tickets/7": () => json(ticket),
  "/api/v1/agreements": () => json([agr(1, "block"), agr(2, "flat")]),
  "/api/v1/tickets/7/time": () => json([entry(5), entry(6, { invoice_line_id: 9 })]),
  ...over,
});

describe("ticket agreement", () => {
  it("saves agreement_id from the select", async () => {
    const calls = run("/tickets/7", STAFF, ticketRoutes({ "/api/v1/tickets/7": (r) => (r.method === "PATCH" ? json(ticket) : json(ticket)) }));
    const sel = await screen.findByLabelText("Agreement");
    await screen.findAllByRole("option", { name: "Plan 1" });
    fireEvent.change(sel, { target: { value: "1" } });
    await waitFor(() => expect(calls.some((c) => c.method === "PATCH" && JSON.parse(c.body!).agreement_id === 1)).toBe(true));
  });

  it("shows the 409 message for a billed entry and locks billed rows", async () => {
    run("/tickets/7", STAFF, ticketRoutes({ "/api/v1/time-entries/5": () => json({ detail: "Time entry is already billed" }, 409) }));
    const sel = await screen.findByLabelText("Agreement for time entry 5");
    await screen.findAllByRole("option", { name: "Plan 2" });
    expect(screen.queryByLabelText("Agreement for time entry 6")).not.toBeInTheDocument();
    fireEvent.change(sel, { target: { value: "2" } });
    expect(await screen.findByText("Time entry is already billed")).toBeInTheDocument();
  });

  it("is read-only without ticket:write", async () => {
    run("/tickets/7", ["ticket:read", "billing:read"], ticketRoutes({ "/api/v1/tickets/7": () => json({ ...ticket, agreement_id: 2 }) }));
    expect(await screen.findByText("Plan 2")).toBeInTheDocument();
    expect(screen.queryByLabelText("Agreement")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Agreement for time entry 5")).not.toBeInTheDocument();
  });
});

describe("agreement settings", () => {
  const BILL = ["org:read", "billing:read", "billing:write"];
  it("offers all-inclusive only for flat agreements", async () => {
    run("/billing/agreements", BILL, {});
    const type = await screen.findByLabelText("Type");
    expect(screen.queryByLabelText(/All-inclusive/)).not.toBeInTheDocument();
    fireEvent.change(type, { target: { value: "flat" } });
    expect(screen.getByLabelText(/All-inclusive/)).toBeInTheDocument();
    fireEvent.change(type, { target: { value: "block" } });
    expect(screen.queryByLabelText(/All-inclusive/)).not.toBeInTheDocument();
    expect(screen.getByLabelText("Unused hours")).toBeInTheDocument();
  });

  it("converts the rollover cap from hours to minutes", async () => {
    const calls = run("/billing/agreements", BILL, { "/api/v1/agreements": (r) => (r.method === "PATCH" ? json({}) : json([agr(1, "block", { rollover: "roll" })])) });
    const cap = await screen.findByLabelText("Plan 1 rollover cap hours");
    fireEvent.change(cap, { target: { value: "2.5" } });
    fireEvent.click(screen.getByRole("button", { name: "Save Plan 1 rollover cap" }));
    await waitFor(() => expect(calls.some((c) => c.method === "PATCH" && JSON.parse(c.body!).rollover_cap_minutes === 150)).toBe(true));
  });

  it("shows settings read-only without billing:write", async () => {
    run("/billing/agreements", ["org:read", "billing:read"], { "/api/v1/agreements": () => json([agr(1, "block", { rollover: "roll", rollover_cap_minutes: 120 })]) });
    expect(await screen.findByText(/rolls over, cap 2 h/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Plan 1 unused hours")).not.toBeInTheDocument();
  });
});

describe("profitability by agreement", () => {
  it("requests group=agreement and the CSV link carries it", async () => {
    const rep = { range: {}, rows: [], totals: { revenue_cents: 0, labour_cost_cents: 0, goods_cost_cents: 0, expense_cost_cents: 0, cost_cents: 0, margin_cents: 0, margin_bp: null, minutes_without_cost_rate: 0, charges_without_cost: 0 } };
    const calls = run("/reports/profitability", ["org:read", "billing:read", "report:read"], { "/api/v1/reports/profitability": () => json(rep) });
    fireEvent.click(await screen.findByLabelText("Agreement"));
    await waitFor(() => expect(calls.some((c) => c.path === "/api/v1/reports/profitability" && c.query.includes("group=agreement"))).toBe(true));
    expect(screen.getByRole("link", { name: "Download CSV" }).getAttribute("href")).toContain("group=agreement");
  });
});
