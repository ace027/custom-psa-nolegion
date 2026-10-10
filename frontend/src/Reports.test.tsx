import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";

const json = (body: unknown) => () => new Response(JSON.stringify(body), { status: 200 });
const me = (role: string, permissions: string[]) => ({ id: 1, email: "u@example.com", display_name: "Una User", role, permissions });
const READ = ["org:read", "user:read", "ticket:read", "billing:read"];
const row = { invoices: 2, time_cents: 0, product_cents: 0, agreement_cents: 30000, manual_cents: 0, subtotal_cents: 30000, tax_cents: 0, total_cents: 30000 };
const handlers = (perms: string[]): Record<string, () => Response> => ({
  "/api/auth/me": json(me("billing", perms)),
  "/api/receivables": json({ as_of: "2026-09-30", rows: [], totals: {} }),
  "/api/billing-notices?status=pending&limit=200": json({ items: [], total: 0, limit: 200, offset: 0 }),
  "/api/reports/revenue": json({ start: "2025-10-01", end: "2026-09-30", clients: [{ organization_id: 1, organization_name: "Acme Corp", ...row }], months: [{ month: "2026-09-01", ...row }], totals: row }),
  "/api/reports/unbilled": json({ through: "2026-09-30", rows: [{ organization_id: 1, organization_name: "Acme Corp", time_entries: 2, billable_minutes: 90, time_value_cents: 22500, unpriced_minutes: 30, oldest_work_date: "2026-09-01", charges: 0, charges_cents: 0, total_cents: 22500 }], totals: { time_entries: 2, billable_minutes: 90, time_value_cents: 22500, unpriced_minutes: 30, charges: 0, charges_cents: 0, total_cents: 22500 } }),
  "/api/reports/recurring?months=12": json({ months: [{ month: "2026-09-01", contracted_cents: 30000, agreements: 1, clients: 1, invoiced_cents: 30000 }] }),
});
function go(path: string, h: Record<string, () => Response>) {
  vi.stubGlobal("fetch", vi.fn((url: string) => Promise.resolve(h[url]?.() ?? new Response("{}", { status: 404 }))));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><MemoryRouter initialEntries={[path]}><App /></MemoryRouter></QueryClientProvider>);
}
afterEach(() => vi.unstubAllGlobals());

describe("reports", () => {
  it("shows revenue, unbilled work (flagging unpriced hours) and CSV links", async () => {
    go("/billing/reports", handlers([...READ, "report:read"]));
    expect(await screen.findByText("Revenue")).toBeInTheDocument();
    expect((await screen.findAllByText("$300.00")).length).toBeGreaterThan(0);
    expect(await screen.findByText(/0\.50 unpriced/)).toBeInTheDocument();
    const links = screen.getAllByRole("link", { name: "Download CSV" }).map((a) => a.getAttribute("href"));
    expect(links).toContain("/api/reports/revenue.csv");
    expect(links).toContain("/api/reports/invoices.csv");
  });

  it("is hidden from people without report access", async () => {
    go("/billing/reports", handlers(READ));
    await screen.findByRole("link", { name: "Rates" });
    expect(screen.queryByRole("link", { name: "Reports" })).toBeNull();
    expect(screen.queryByText("Revenue")).toBeNull();
  });
});
