import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";

const json = (body: unknown, status = 200) => () => new Response(JSON.stringify(body), { status });
const me = { id: 1, email: "b@example.com", display_name: "Bea Biller", role: "billing", permissions: ["org:read", "user:read", "ticket:read", "billing:read", "billing:write", "billing:finalize", "payment:write"] };
const row = {
  invoice_id: 9, invoice_number: "INV-2026-0042", organization_id: 1, organization_name: "Acme", due_date: "2026-08-29", days_overdue: 40,
  balance_cents: 100000, base_cents: 100000, percent_bp: 150, percent_fee_cents: 1500, flat_fee_cents: 1000, fee_cents: 2500, fees_so_far: 0,
};
const base: Record<string, (init?: RequestInit) => Response> = {
  "/api/auth/me": json(me),
  "/api/organizations": json({ items: [], total: 0 }),
  "/api/receivables": json({ as_of: "2026-10-08", rows: [], totals: { overdue_invoice_count: 0 } }),
  "/api/billing-notices": json({ items: [], total: 0 }),
};

function mount(path: string, extra: Record<string, (init?: RequestInit) => Response>) {
  const handlers = { ...base, ...extra };
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => Promise.resolve(handlers[url.split("?")[0]]?.(init) ?? new Response("[]", { status: 200 }))),
  );
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}><App /></MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("late fees", () => {
  it("previews qualifying invoices and applies only the ticked ones", async () => {
    const posts: string[] = [];
    mount("/billing/late-fees", {
      "/api/late-fees/preview": json({ configured: true, percent_bp: 150, flat_cents: 1000, grace_days: 15, max_per_invoice: 1, rows: [row] }),
      "/api/late-fees/apply": (init) => { posts.push(String(init?.body)); return new Response("[]", { status: 201 }); },
    });
    expect(await screen.findByText("INV-2026-0042")).toBeTruthy();
    expect(screen.getByText("$25.00")).toBeTruthy();
    fireEvent.click(screen.getByLabelText("Charge INV-2026-0042"));
    fireEvent.click(screen.getByRole("button", { name: "Charge 1 late fee" }));
    await waitFor(() => expect(posts).toHaveLength(1));
    expect(JSON.parse(posts[0])).toEqual({ invoice_ids: [9] });
  });

  it("tells the user when no rule is set", async () => {
    mount("/billing/late-fees", {
      "/api/late-fees/preview": json({ configured: false, percent_bp: 0, flat_cents: 0, grace_days: 15, max_per_invoice: 1, rows: [] }),
    });
    expect(await screen.findByText(/No late-fee rule is set/)).toBeTruthy();
  });
});
