import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";

const json = (body: unknown, status = 200) => () => new Response(JSON.stringify(body), { status });
const me = (role: string, permissions: string[]) => ({ id: 1, email: "u@example.com", display_name: "Una User", role, permissions });
const READ = ["org:read", "user:read", "ticket:read", "billing:read"];
const BILL = [...READ, "billing:write", "billing:finalize", "charge:write", "payment:write"];

const invoice = (over = {}) => ({
  id: 5, number: null, organization_id: 1, organization_name: "Acme Corp", status: "draft", billing_run_id: null,
  period_start: null, period_end: null, invoice_date: null, due_date: null, terms_days: null,
  subtotal_cents: 30000, tax_cents: 2475, total_cents: 32475, memo: null, warnings: [], void_reason: null,
  created_at: "2026-09-30T12:00:00Z", paid_cents: null, written_off_cents: null, balance_cents: null,
  payment_status: null, is_overdue: false, days_past_due: 0, payments: [], write_offs: [], lines: [
    { id: 11, kind: "agreement", description: "Managed Services: 25 users x $12.00 (Sep 2026)", quantity: "25.0000", unit_price_cents: 1200, amount_cents: 30000, tax_rate_bp: 825, tax_cents: 2475 },
  ], ...over,
});
const run = (over = {}) => ({
  id: 9, period_start: "2026-10-01", period_end: "2026-10-31", status: "draft", created_at: "2026-09-30T12:00:00Z",
  reviewed_at: null, finalized_at: null, invoice_count: 1, total_cents: 32475,
  warnings: ["Acme Corp: No hourly rate for work type 'Onsite': 2 time entries (90 min) left unbilled"],
  invoices: [invoice({ billing_run_id: 9 })], ...over,
});

function go(path: string, handlers: Record<string, () => Response>) {
  vi.stubGlobal("fetch", vi.fn((url: string) => Promise.resolve(handlers[url]?.() ?? new Response("{}", { status: 404 }))));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}><App /></MemoryRouter>
    </QueryClientProvider>,
  );
}
afterEach(() => vi.unstubAllGlobals());

describe("invoice page", () => {
  it("lets billing edit a draft: editable lines, add line, unbilled, finalize, PDF", async () => {
    go("/billing/invoices/5", { "/api/auth/me": json(me("billing", BILL)), "/api/invoices/5": json(invoice()) });
    expect(await screen.findByText("Draft invoice #5")).toBeInTheDocument();
    expect(screen.getByLabelText("Line description")).toHaveValue("Managed Services: 25 users x $12.00 (Sep 2026)");
    expect(screen.getByLabelText("Line quantity")).toHaveValue("25");
    expect(screen.getByLabelText("Line unit price")).toHaveValue("12.00");
    expect(screen.getByLabelText("Line tax percent")).toHaveValue("8.25");
    expect(screen.getByText("$324.75")).toBeInTheDocument(); // total
    expect(screen.getByRole("button", { name: "Finalize invoice" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add line" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Add unbilled/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Download PDF" })).toHaveAttribute("href", "/api/invoices/5/pdf");
  });

  it("shows a finalized invoice as frozen: no edit controls, even for billing", async () => {
    go("/billing/invoices/5", {
      "/api/auth/me": json(me("billing", BILL)),
      "/api/invoices/5": json(invoice({ status: "final", number: "INV-2026-0001", invoice_date: "2026-09-30", due_date: "2026-10-30", terms_days: 30, paid_cents: 0, written_off_cents: 0, balance_cents: 32475, payment_status: "unpaid" })),
    });
    expect(await screen.findByText("INV-2026-0001")).toBeInTheDocument();
    expect(screen.getByText(/This invoice is frozen/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Line description")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add line" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Finalize invoice" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Void invoice" })).toBeInTheDocument();
  });

  it("gives read-only users nothing to click", async () => {
    go("/billing/invoices/5", { "/api/auth/me": json(me("read_only", READ)), "/api/invoices/5": json(invoice()) });
    expect(await screen.findByText("Draft invoice #5")).toBeInTheDocument();
    expect(screen.queryByLabelText("Line description")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Finalize invoice" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Discard|Void/ })).not.toBeInTheDocument();
  });

  it("sends draft invoices that belong to a run to the run for finalizing", async () => {
    go("/billing/invoices/5", { "/api/auth/me": json(me("billing", BILL)), "/api/invoices/5": json(invoice({ billing_run_id: 9 })) });
    expect(await screen.findByText(/finalize it from the run/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Finalize invoice" })).not.toBeInTheDocument();
  });
});

describe("billing run page", () => {
  it("shows warnings and guides the draft -> reviewed step", async () => {
    go("/billing/runs/9", { "/api/auth/me": json(me("billing", BILL)), "/api/billing-runs/9": json(run()) });
    expect(await screen.findByText("Billing run 2026-10")).toBeInTheDocument();
    expect(screen.getByText(/Warnings \(1\)/)).toBeInTheDocument();
    expect(screen.getByText(/left unbilled/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Mark reviewed" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Finalize all invoices" })).not.toBeInTheDocument(); // must review first
    expect(screen.getByRole("button", { name: "Cancel run" })).toBeInTheDocument();
  });

  it("offers finalize only after review", async () => {
    go("/billing/runs/9", { "/api/auth/me": json(me("billing", BILL)), "/api/billing-runs/9": json(run({ status: "reviewed", reviewed_at: "2026-09-30T13:00:00Z" })) });
    expect(await screen.findByRole("button", { name: "Finalize all invoices" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Mark reviewed" })).not.toBeInTheDocument();
  });

  it("has no action buttons once finalized or for read-only users", async () => {
    go("/billing/runs/9", { "/api/auth/me": json(me("billing", BILL)), "/api/billing-runs/9": json(run({ status: "finalized" })) });
    expect(await screen.findByText("Billing run 2026-10")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /review|Finalize|Cancel/i })).not.toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  it("hides run actions from read-only users", async () => {
    go("/billing/runs/9", { "/api/auth/me": json(me("read_only", READ)), "/api/billing-runs/9": json(run()) });
    expect(await screen.findByText("Billing run 2026-10")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Mark reviewed" })).not.toBeInTheDocument();
  });
});

describe("navigation", () => {
  it("shows the Billing menu to those who can read billing, and hides it otherwise", async () => {
    go("/dashboard", {
      "/api/auth/me": json(me("tech", ["org:read", "user:read", "ticket:read"])),
      "/api/dashboard": json({ my_open: [], unassigned: [], sla_at_risk: [], counts: { open: 0, mine: 0, unassigned: 0, sla_at_risk: 0, needs_triage: 0 } }),
    });
    expect(await screen.findByText("Dashboard", { selector: "h1" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Billing" })).not.toBeInTheDocument();
  });
});
