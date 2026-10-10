import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";

const json = (body: unknown, status = 200) => () => new Response(JSON.stringify(body), { status });
const me = { id: 1, email: "b@example.com", display_name: "Bea Biller", role: "billing", permissions: ["org:read", "user:read", "ticket:read", "billing:read", "billing:write"] };

afterEach(() => vi.unstubAllGlobals());

function mount(path: string, handlers: Record<string, (init?: RequestInit) => Response>) {
  const all: Record<string, (init?: RequestInit) => Response> = {
    "/api/auth/me": json(me),
    "/api/agreements": json([]),
    "/api/receivables": json({ as_of: "2026-10-08", rows: [], totals: { overdue_invoice_count: 0 } }),
    "/api/billing-notices": json({ items: [], total: 0 }),
    "/api/organizations": json({ items: [{ id: 1, name: "Acme" }], total: 1 }),
    ...handlers,
  };
  vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => Promise.resolve(all[url.split("?")[0]]?.(init) ?? new Response("[]", { status: 200 }))));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={qc}><MemoryRouter initialEntries={[path]}><App /></MemoryRouter></QueryClientProvider>);
}

async function fillBlock() {
  const type = await screen.findByLabelText("Type");
  await screen.findByRole("option", { name: "Acme" });
  fireEvent.change(screen.getAllByRole("combobox")[0], { target: { value: "1" } });
  fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Support block" } });
  fireEvent.change(type, { target: { value: "block" } });
  fireEvent.change(screen.getByLabelText("Monthly fee ($)"), { target: { value: "1000" } });
}

describe("block agreements", () => {
  it("shows Included hours and hides quantity for Block hours", async () => {
    mount("/billing/agreements", {});
    fireEvent.change(await screen.findByLabelText("Type"), { target: { value: "block" } });
    expect(screen.getByLabelText("Included hours")).toBeInTheDocument();
    expect(screen.queryByLabelText("Users")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Monthly fee ($)")).toBeInTheDocument();
  });

  it("posts block_minutes 600 and quantity 1 for 10 hours", async () => {
    const posts: string[] = [];
    mount("/billing/agreements", {
      "/api/agreements": (init) => { if (init?.method === "POST") { posts.push(String(init.body)); return new Response("{}", { status: 201 }); } return new Response("[]"); },
    });
    await fillBlock();
    fireEvent.change(screen.getByLabelText("Included hours"), { target: { value: "10" } });
    fireEvent.click(screen.getByRole("button", { name: "Create agreement" }));
    await waitFor(() => expect(posts).toHaveLength(1));
    const body = JSON.parse(posts[0]);
    expect(body.block_minutes).toBe(600);
    expect(body.quantity).toBe(1);
    expect(body.type).toBe("block");
  });

  it("shows the 409 detail inline", async () => {
    mount("/billing/agreements", {
      "/api/agreements": (init) => init?.method === "POST" ? new Response(JSON.stringify({ detail: "Overlaps an existing block agreement" }), { status: 409 }) : new Response("[]"),
    });
    await fillBlock();
    fireEvent.change(screen.getByLabelText("Included hours"), { target: { value: "7.5" } });
    fireEvent.click(screen.getByRole("button", { name: "Create agreement" }));
    expect(await screen.findByText(/Overlaps an existing block agreement/)).toBeInTheDocument();
  });

  it("sends block_covered false from the Rates checkbox", async () => {
    const patches: string[] = [];
    const wt = { id: 3, name: "Onsite", rate_cents: 20000, taxable: true, block_covered: true, archived_at: null };
    mount("/billing/rates", {
      "/api/billing/work-types": json([wt]),
      "/api/billing/work-types/3": (init) => { patches.push(String(init?.body)); return new Response(JSON.stringify(wt)); },
    });
    fireEvent.click(await screen.findByLabelText("Onsite not covered by blocks"));
    await waitFor(() => expect(patches).toHaveLength(1));
    expect(JSON.parse(patches[0])).toEqual({ block_covered: false });
  });
});
