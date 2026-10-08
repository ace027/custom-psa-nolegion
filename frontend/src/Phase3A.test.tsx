import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";

const json = (body: unknown, status = 200) => () => new Response(JSON.stringify(body), { status });
const me = { id: 1, email: "b@example.com", display_name: "Bea Biller", role: "billing", permissions: ["org:read", "user:read", "ticket:read", "billing:read", "billing:write"] };
const agreement = {
  id: 4, organization_id: 1, organization_name: "Acme", name: "Devices", type: "per_device", unit_price_cents: 2500, quantity: 40,
  taxable: false, start_date: "2026-01-01", end_date: null, notes: null, monthly_amount_cents: 100000,
};

afterEach(() => vi.unstubAllGlobals());

describe("NinjaOne device count suggestion", () => {
  it("shows the difference and only changes the quantity after a click, with a reason", async () => {
    const patches: string[] = [];
    const handlers: Record<string, (init?: RequestInit) => Response> = {
      "/api/auth/me": json(me),
      "/api/agreements": json([agreement]),
      "/api/organizations": json({ items: [], total: 0 }),
      "/api/receivables": json({ as_of: "2026-10-08", rows: [], totals: { overdue_invoice_count: 0 } }),
      "/api/billing-notices": json({ items: [], total: 0 }),
      "/api/agreements/4/device-count": json({ ninjaone_devices: 42, agreement_quantity: 40, differs: true }),
      "/api/agreements/4": (init) => { patches.push(String(init?.body)); return new Response(JSON.stringify(agreement)); },
    };
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init?: RequestInit) => Promise.resolve(handlers[url.split("?")[0]]?.(init) ?? new Response("[]", { status: 200 }))),
    );
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={["/billing/agreements"]}><App /></MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByText(/NinjaOne reports 42 devices; this agreement says 40/)).toBeInTheDocument();
    expect(patches).toHaveLength(0); // showing the suggestion changes nothing
    fireEvent.click(screen.getByRole("button", { name: "Update quantity to 42" }));
    await waitFor(() => expect(patches).toHaveLength(1));
    expect(JSON.parse(patches[0])).toEqual({ quantity: 42, reason: "Updated from NinjaOne device count" });
  });
});
