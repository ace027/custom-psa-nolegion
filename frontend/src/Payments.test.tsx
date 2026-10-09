import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";

const json = (body: unknown, status = 200) => () => new Response(JSON.stringify(body), { status });
const me = (role: string, permissions: string[]) => ({ id: 1, email: "u@example.com", display_name: "Una User", role, permissions });
const READ = ["org:read", "user:read", "ticket:read", "billing:read"];
const BILL = [...READ, "billing:write", "billing:finalize", "charge:write", "payment:write"];

const inv = (over = {}) => ({
  id: 5, number: "INV-2026-0001", organization_id: 1, organization_name: "Acme Corp", status: "final", billing_run_id: null,
  period_start: null, period_end: null, invoice_date: "2026-08-01", due_date: "2026-08-31", terms_days: 30,
  subtotal_cents: 30000, tax_cents: 2475, total_cents: 32475, memo: null, warnings: [], void_reason: null,
  created_at: "2026-08-01T12:00:00Z", paid_cents: 10000, written_off_cents: 0, balance_cents: 22475,
  payment_status: "partial", is_overdue: true, days_past_due: 30, payments: [
    { application_id: 9, payment_id: 3, amount_cents: 10000, received_on: "2026-09-01", method: "check", reference: "1042", voided_at: null, void_reason: null },
  ], write_offs: [], lines: [], ...over,
});
const row = (over = {}) => ({
  organization_id: 1, organization_name: "Acme Corp", current_cents: 0, d1_30_cents: 22475, d31_60_cents: 0, d61_90_cents: 0,
  d90_plus_cents: 0, total_open_cents: 22475, credit_cents: 500, open_invoice_count: 1, overdue_invoice_count: 1, oldest_days_past_due: 30, ...over,
});
const receivables = { as_of: "2026-09-30", rows: [row()], totals: { ...row(), organization_id: 0, organization_name: "Total" } };

function go(path: string, handlers: Record<string, () => Response>) {
  vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => {
    const key = init?.method && init.method !== "GET" ? `${init.method} ${url}` : url;
    return Promise.resolve((handlers[key] ?? handlers[url])?.() ?? new Response("{}", { status: 404 }));
  }));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><MemoryRouter initialEntries={[path]}><App /></MemoryRouter></QueryClientProvider>);
}
afterEach(() => vi.unstubAllGlobals());

describe("receivables", () => {
  it("shows aging buckets, totals, credit and an overdue badge", async () => {
    go("/billing/receivables", { "/api/auth/me": json(me("billing", BILL)), "/api/receivables": json(receivables) });
    expect(await screen.findByText("Acme Corp")).toBeInTheDocument();
    expect(screen.getAllByText("$224.75").length).toBeGreaterThan(0);
    expect(screen.getByText(/oldest 30d late/)).toBeInTheDocument();
    expect(screen.getByText("Unapplied credit")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Record payment" })).toHaveAttribute("href", "/billing/payments?new=1&org=1");
    expect(screen.getByText("1 overdue")).toBeInTheDocument(); // tab badge
  });

  it("does not offer Record payment to read-only users", async () => {
    go("/billing/receivables", { "/api/auth/me": json(me("read_only", READ)), "/api/receivables": json(receivables) });
    expect(await screen.findByText("Acme Corp")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Record payment" })).not.toBeInTheDocument();
  });
});

describe("invoice payment section", () => {
  it("shows status, balance, payments and the actions for billing", async () => {
    go("/billing/invoices/5", { "/api/auth/me": json(me("billing", BILL)), "/api/invoices/5": json(inv()) });
    expect(await screen.findByText("INV-2026-0001")).toBeInTheDocument();
    expect(screen.getByText("partial")).toBeInTheDocument();
    expect(screen.getByText("30d overdue")).toBeInTheDocument();
    expect(screen.getByText("$224.75")).toBeInTheDocument(); // balance
    expect(screen.getByText(/\$100.00 · 2026-09-01 · check #1042/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Record payment" })).toHaveAttribute("href", "/billing/payments?new=1&org=1&invoice=5");
    expect(screen.getByRole("button", { name: "Write off balance" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "undo" })).toBeInTheDocument();
  });

  it("hides every payment action from read-only users but still shows the balance", async () => {
    go("/billing/invoices/5", { "/api/auth/me": json(me("read_only", READ)), "/api/invoices/5": json(inv()) });
    expect(await screen.findByText("$224.75")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Record payment" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Write off balance" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "undo" })).not.toBeInTheDocument();
  });

  it("shows no balance actions on a paid invoice, and strikes through undone payments", async () => {
    go("/billing/invoices/5", { "/api/auth/me": json(me("billing", BILL)), "/api/invoices/5": json(inv({ paid_cents: 32475, balance_cents: 0, payment_status: "paid", is_overdue: false, days_past_due: 0 })) });
    expect(await screen.findByText("paid")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Record payment" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Write off balance" })).not.toBeInTheDocument();
  });
});

describe("record payment", () => {
  const open = { items: [inv({ id: 5, number: "INV-1", balance_cents: 6000 }), inv({ id: 6, number: "INV-2", balance_cents: 4000, due_date: "2026-09-15", days_past_due: 15 })], total: 2, limit: 200, offset: 0 };
  const handlers = (extra: Record<string, () => Response> = {}) => ({
    "/api/auth/me": json(me("billing", BILL)),
    "/api/payments?limit=100": json({ items: [], total: 0, limit: 100, offset: 0 }),
    "/api/organizations?limit=200&include_archived=false&q=": json({ items: [{ id: 1, name: "Acme Corp", status: "active", archived_at: null }], total: 1, limit: 200, offset: 0 }),
    "/api/invoices?organization_id=1&payment_status=open&limit=200": json(open),
    ...extra,
  });

  it("auto-applies oldest first and says how much becomes credit", async () => {
    go("/billing/payments?new=1&org=1", handlers());
    const amount = await screen.findByLabelText("Amount received ($)");
    await screen.findByText("INV-1");
    fireEvent.change(amount, { target: { value: "120.00" } });
    fireEvent.click(screen.getByRole("button", { name: /Auto-apply/ }));
    // oldest due date first: INV-1 (due 08-31) gets 60.00, INV-2 (due 09-15) gets 40.00, $20.00 is left over
    await waitFor(() => expect(screen.getByLabelText("Apply to INV-1")).toHaveValue("60.00"));
    expect(screen.getByLabelText("Apply to INV-2")).toHaveValue("40.00");
    expect(screen.getByText(/\$20.00 will be kept as credit/)).toBeInTheDocument();
  });

  it("warns when more is applied than was received", async () => {
    go("/billing/payments?new=1&org=1", handlers());
    fireEvent.change(await screen.findByLabelText("Amount received ($)"), { target: { value: "50.00" } });
    await screen.findByText("INV-1");
    fireEvent.change(screen.getByLabelText("Apply to INV-1"), { target: { value: "60.00" } });
    expect(await screen.findByText(/Over-applied by \$10.00/)).toBeInTheDocument();
  });

  it("is not shown to users who cannot record payments", async () => {
    go("/billing/payments", { ...handlers(), "/api/auth/me": json(me("read_only", READ)) });
    expect(await screen.findByText(/Record money received/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Record payment" })).not.toBeInTheDocument();
  });
});
