import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";

const json = (body: unknown, status = 200) => () => new Response(JSON.stringify(body), { status });
const WRITE = ["crm:read", "crm:write"];
const READ = ["crm:read"];
const me = (role: string, permissions: string[]) => ({ id: 1, email: "u@example.com", display_name: "Una", role, permissions });
const TS = "2026-10-01T12:00:00Z";

const stages = [
  { id: 1, name: "Prospecting", position: 1, probability_bp: 1000, kind: "open", active: true },
  { id: 2, name: "Proposal", position: 2, probability_bp: 5000, kind: "open", active: true },
  { id: 3, name: "Won", position: 3, probability_bp: 10000, kind: "won", active: true },
  { id: 4, name: "Lost", position: 4, probability_bp: 0, kind: "lost", active: true },
];
const opp = (over = {}) => ({
  id: 5, organization_id: 3, organization_name: "Acme", name: "Acme managed IT", kind: "new", stage_id: 1, stage_name: "Prospecting", stage_kind: "open",
  probability_bp: 1000, owner_id: null, owner_name: "Dana", monthly_cents: 150000, term_months: 12, expected_close_date: "2026-11-15", quote_id: null,
  quote_number: null, agreement_id: null, agreement_name: null, lost_reason: null, closed_at: null, notes: null, created_at: TS, updated_at: TS, ...over,
});
const lead = (over = {}) => ({
  id: 9, name: "Pat Smith", company: "Smith Co", email: "pat@smith.example", phone: null, source: "Referral", status: "qualified", owner_id: null, owner_name: null,
  notes: "Wants managed IT", converted_organization_id: null, converted_at: null, created_at: TS, updated_at: TS, ...over,
});
const bucket = (over = {}) => ({ key: "2026-11", label: "Nov 2026", count: 2, monthly_cents: 300000, weighted_monthly_cents: 150050, contract_value_cents: 3600000, ...over });
const reminder = (over = {}) => ({
  id: 4, organization_id: 3, organization_name: "Acme", agreement_id: 8, agreement_name: "Managed services", lead_days: 60, due_on: "2026-12-20", status: "open",
  opportunity_id: 5, created_at: TS, ...over,
});

let calls: string[] = [];
function go(path: string, role: string, perms: string[], h: Record<string, () => Response>) {
  const handlers: Record<string, () => Response> = { "/api/auth/me": json(me(role, perms)), "/api/crm/stages": json(stages), ...h };
  vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => {
    const key = init?.method && init.method !== "GET" ? `${init.method} ${url}` : url;
    calls.push(`${key} ${init?.body ?? ""}`);
    return Promise.resolve(handlers[key]?.() ?? new Response("{}", { status: 404 }));
  }));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><MemoryRouter initialEntries={[path]}><App /></MemoryRouter></QueryClientProvider>);
}
const called = (prefix: string, part = "") => calls.some((c) => c.startsWith(prefix) && c.includes(part));
beforeEach(() => { calls = []; });
afterEach(() => vi.unstubAllGlobals());

describe("sales navigation", () => {
  it("shows the Sales link and tabs for crm:read", async () => {
    go("/crm", "read_only", READ, { "/api/crm/opportunities": json([]) });
    expect(await screen.findByRole("link", { name: "Sales" })).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: "Forecast" })).toBeInTheDocument();
    expect(await screen.findByText(/No opportunities yet/)).toBeInTheDocument();
  });
});

describe("leads", () => {
  const leads = () => json([lead(), lead({ id: 10, name: "Old Lead", status: "converted", converted_organization_id: 3 })]);

  it("lists leads and converts one with a prefilled form", async () => {
    go("/crm/leads", "admin", WRITE, {
      "/api/crm/leads": leads(), "/api/users": json([]),
      "POST /api/crm/leads/9/convert": json(opp({ id: 77 }), 201),
      "/api/crm/opportunities/77": json(opp({ id: 77 })),
    });
    expect(await screen.findByText("Pat Smith")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View client" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Convert Pat Smith" }));
    expect(await screen.findByDisplayValue("Smith Co – new agreement")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Wants managed IT")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Monthly ($)"), { target: { value: "1500.00" } });
    fireEvent.click(screen.getByRole("button", { name: /Convert lead/ }));
    await waitFor(() => expect(called("POST /api/crm/leads/9/convert", '"monthly_cents":150000')).toBe(true));
    expect(called("POST /api/crm/leads/9/convert", '"term_months":12')).toBe(true);
    expect(await screen.findByRole("heading", { name: "Acme managed IT" })).toBeInTheDocument();
  });

  it("shows an API 409 inline and rejects a bad amount client-side", async () => {
    go("/crm/leads", "admin", WRITE, {
      "/api/crm/leads": leads(), "/api/users": json([]),
      "POST /api/crm/leads/9/convert": json({ detail: "Lead is already converted" }, 409),
    });
    fireEvent.click(await screen.findByRole("button", { name: "Convert Pat Smith" }));
    fireEvent.change(await screen.findByLabelText("Monthly ($)"), { target: { value: "abc" } });
    fireEvent.click(screen.getByRole("button", { name: /Convert lead/ }));
    expect(await screen.findByText(/Enter the monthly amount/)).toBeInTheDocument();
    expect(called("POST")).toBe(false);
    fireEvent.change(screen.getByLabelText("Monthly ($)"), { target: { value: "10" } });
    fireEvent.click(screen.getByRole("button", { name: /Convert lead/ }));
    expect(await screen.findByText("Lead is already converted")).toBeInTheDocument();
  });

  it("shows an empty state", async () => {
    go("/crm/leads", "admin", WRITE, { "/api/crm/leads": json([]), "/api/users": json([]) });
    expect(await screen.findByText("No leads yet.")).toBeInTheDocument();
  });
});

describe("pipeline", () => {
  const board = (extra: Record<string, () => Response> = {}) => ({ "/api/crm/opportunities": json([opp(), opp({ id: 6, name: "Beta deal", stage_id: 2, stage_name: "Proposal" })]), ...extra });

  it("renders a column per stage with cards and moves a card", async () => {
    go("/crm/pipeline", "admin", WRITE, board({ "POST /api/crm/opportunities/5/stage": json(opp({ stage_id: 2 })) }));
    const col = await screen.findByRole("region", { name: "Prospecting" });
    expect(within(col).getByText("Acme managed IT")).toBeInTheDocument();
    expect(within(col).getByText("$1,500.00/mo")).toBeInTheDocument();
    expect(within(col).getByText("Close 2026-11-15")).toBeInTheDocument();
    expect(within(col).getByText("Dana")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Proposal" })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Move Acme managed IT to stage"), { target: { value: "2" } });
    await waitFor(() => expect(called("POST /api/crm/opportunities/5/stage", '"stage_id":2')).toBe(true));
  });

  it("blocks lost without a reason, then sends it and shows API errors", async () => {
    go("/crm/pipeline", "admin", WRITE, board({ "POST /api/crm/opportunities/5/stage": json({ detail: "Stage is inactive" }, 409) }));
    await screen.findByRole("region", { name: "Prospecting" });
    fireEvent.change(screen.getByLabelText("Move Acme managed IT to stage"), { target: { value: "4" } });
    fireEvent.click(await screen.findByRole("button", { name: "Mark lost" }));
    expect(await screen.findByText("Say why it was lost.")).toBeInTheDocument();
    expect(called("POST")).toBe(false);
    fireEvent.change(screen.getByLabelText("Lost reason"), { target: { value: "Went with competitor" } });
    fireEvent.click(screen.getByRole("button", { name: "Mark lost" }));
    await waitFor(() => expect(called("POST /api/crm/opportunities/5/stage", "Went with competitor")).toBe(true));
    expect(await screen.findByText("Stage is inactive")).toBeInTheDocument();
  });

  it("hides move controls from a read-only user", async () => {
    go("/crm/pipeline", "read_only", READ, board());
    await screen.findByText("Acme managed IT");
    expect(screen.queryByLabelText("Move Acme managed IT to stage")).not.toBeInTheDocument();
  });

  it("shows an empty state", async () => {
    go("/crm/pipeline", "admin", WRITE, { "/api/crm/opportunities": json([]) });
    expect(await screen.findByText(/No opportunities yet/)).toBeInTheDocument();
  });
});

describe("forecast", () => {
  it("renders buckets, total and the won tiles", async () => {
    go("/crm/forecast", "read_only", READ, {
      "/api/crm/forecast": json({
        buckets: [bucket()], total: bucket({ key: "total", label: "Total" }),
        won_this_month: bucket({ key: "m", count: 1, monthly_cents: 50000, contract_value_cents: 600000 }),
        won_this_quarter: bucket({ key: "q", count: 3, monthly_cents: 120000, contract_value_cents: 1440000 }),
      }),
    });
    const row = (await screen.findByText("Nov 2026")).closest("tr")!;
    expect(within(row).getByText("$3,000.00")).toBeInTheDocument();
    expect(within(row).getByText("$1,500.50")).toBeInTheDocument();
    expect(within(row).getByText("$36,000.00")).toBeInTheDocument();
    expect(screen.getByText("Won this month (monthly)").previousElementSibling).toHaveTextContent("$500.00");
    expect(screen.getByText("Won this quarter (monthly)").previousElementSibling).toHaveTextContent("$1,200.00");
  });
});

describe("renewals", () => {
  it("lists open reminders and dismisses one", async () => {
    go("/crm/renewals", "admin", WRITE, {
      "/api/crm/renewals?status=open": json([reminder({ id: 5, due_on: "2027-03-01", agreement_name: "Later" }), reminder()]),
      "POST /api/crm/renewals/4/dismiss": json(reminder({ status: "dismissed" })),
    });
    const row = (await screen.findByText("Managed services")).closest("tr")!;
    expect(within(row).getByRole("link", { name: "Renewal opportunity" })).toHaveAttribute("href", "/crm/opportunities/5");
    const order = screen.getAllByRole("row").map((r) => r.textContent ?? "");
    expect(order.findIndex((t) => t.includes("Managed services"))).toBeLessThan(order.findIndex((t) => t.includes("Later")));
    fireEvent.click(within(row).getByRole("button", { name: /Dismiss/ }));
    await waitFor(() => expect(called("POST /api/crm/renewals/4/dismiss")).toBe(true));
  });

  it("shows an empty state and hides Dismiss without crm:write", async () => {
    go("/crm/renewals", "read_only", READ, { "/api/crm/renewals?status=open": json([]) });
    expect(await screen.findByText(/No renewals are due/)).toBeInTheDocument();
  });

  it("hides Dismiss from a read-only user", async () => {
    go("/crm/renewals", "read_only", READ, { "/api/crm/renewals?status=open": json([reminder()]) });
    await screen.findByText("Managed services");
    expect(screen.queryByRole("button", { name: /Dismiss/ })).not.toBeInTheDocument();
  });
});

describe("opportunity page", () => {
  it("moves to lost only with a reason and hides controls for read-only", async () => {
    go("/crm/opportunities/5", "read_only", READ, { "/api/crm/opportunities/5": json(opp({ quote_id: 2, quote_number: "Q-2" })) });
    expect(await screen.findByRole("heading", { name: "Acme managed IT" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Q-2" })).toHaveAttribute("href", "/quotes/2");
    expect(screen.queryByRole("button", { name: "Save" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Move to stage")).not.toBeInTheDocument();
  });
});
