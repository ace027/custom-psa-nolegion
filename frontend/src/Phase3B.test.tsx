import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";

const json = (body: unknown, status = 200) => () => new Response(JSON.stringify(body), { status });
const me = { id: 1, email: "b@example.com", display_name: "Bea Biller", role: "billing", permissions: ["org:read", "user:read", "ticket:read", "billing:read", "billing:write", "billing:finalize", "payment:write"] };
const memo = {
  id: 3, number: "CM-2026-0001", organization_id: 1, organization_name: "Acme", memo_date: "2026-10-08", reason: "Billed in error", invoice_id: null,
  subtotal_cents: 14197, tax_cents: 1171, total_cents: 15368, status: "active", applied_cents: 0, unapplied_cents: 15368, void_reason: null, created_at: "2026-10-08T12:00:00Z",
};
const base: Record<string, (init?: RequestInit) => Response> = {
  "/api/auth/me": json(me),
  "/api/organizations": json({ items: [{ id: 1, name: "Acme" }], total: 1 }),
  "/api/receivables": json({ as_of: "2026-10-08", rows: [], totals: { overdue_invoice_count: 0 } }),
  "/api/billing-notices": json({ items: [], total: 0 }),
  "/api/invoices": json({ items: [{ id: 9, number: "INV-2026-0042", organization_id: 1, due_date: "2026-11-01", balance_cents: 15368, is_overdue: false, days_past_due: 0 }], total: 1 }),
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

describe("credit memos", () => {
  it("lists memos and applies unapplied credit to an open invoice", async () => {
    const posts: string[] = [];
    mount("/billing/credit-memos", {
      "/api/credit-memos": () => new Response(JSON.stringify({ items: [memo], total: 1, limit: 100, offset: 0 })),
      "/api/credit-memos/3": json({ ...memo, lines: [{ position: 1, description: "Correction", quantity: "1.0000", unit_price_cents: 14197, amount_cents: 14197, tax_cents: 1171 }], applications: [] }),
      "/api/credit-memos/3/apply": (init) => { posts.push(String(init?.body)); return new Response(JSON.stringify(memo)); },
    });
    expect(await screen.findByText("CM-2026-0001")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "details" }));
    expect(await screen.findByText(/Correction: 1.0000/)).toBeInTheDocument();
    const select = await screen.findByLabelText(/Apply credit/);
    await screen.findByRole("option", { name: /INV-2026-0042/ });
    fireEvent.change(select, { target: { value: "9" } });
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    await waitFor(() => expect(posts).toHaveLength(1));
    expect(JSON.parse(posts[0])).toEqual({ invoice_id: 9, amount_cents: 15368 });
  });

  it("issues a memo from positive line amounts", async () => {
    const posts: string[] = [];
    mount("/billing/credit-memos", {
      "/api/credit-memos": (init) => {
        if (init?.method === "POST") { posts.push(String(init.body)); return new Response(JSON.stringify(memo), { status: 201 }); }
        return new Response(JSON.stringify({ items: [], total: 0, limit: 100, offset: 0 }));
      },
    });
    const client = await screen.findByLabelText("Client");
    await screen.findByRole("option", { name: "Acme" });
    fireEvent.change(client, { target: { value: "1" } });
    fireEvent.change(screen.getByLabelText(/^Reason/), { target: { value: "Billed in error" } });
    fireEvent.change(screen.getByLabelText("Line 1 description"), { target: { value: "Correction" } });
    fireEvent.change(screen.getByLabelText("Unit price ($)"), { target: { value: "141.97" } });
    fireEvent.click(screen.getByLabelText("Taxable"));
    fireEvent.click(screen.getByRole("button", { name: "Issue credit memo" }));
    await waitFor(() => expect(posts).toHaveLength(1));
    expect(JSON.parse(posts[0])).toEqual({
      organization_id: 1, reason: "Billed in error", invoice_id: null,
      lines: [{ description: "Correction", quantity: "1", unit_price_cents: 14197, taxable: true }],
    });
  });
});
