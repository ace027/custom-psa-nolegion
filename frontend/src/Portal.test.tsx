import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";

const json = (body: unknown, status = 200) => () => new Response(JSON.stringify(body), { status });
const me = (over = {}) => ({ contact_name: "Pat Payer", email: "pat@acme.com", organization_name: "Acme Corp", company_name: "Acme MSP", can_see_billing: false, can_see_all_tickets: false, ...over });
const ticket = { id: 3, number: 10003, subject: "VPN slow", status: "open", created_at: "2026-09-30T12:00:00Z", updated_at: "2026-09-30T12:00:00Z", mine: true };

function go(path: string, handlers: Record<string, () => Response>, calls: string[] = []) {
  vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => {
    const key = init?.method && init.method !== "GET" ? `${init.method} ${url}` : url;
    calls.push(`${key} ${init?.body ?? ""}`);
    return Promise.resolve(handlers[key]?.() ?? new Response("{}", { status: 404 }));
  }));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><MemoryRouter initialEntries={[path]}><App /></MemoryRouter></QueryClientProvider>);
}
afterEach(() => { vi.unstubAllGlobals(); window.location.hash = ""; });

describe("client portal", () => {
  it("asks for an email and shows the same answer regardless of who they are", async () => {
    const calls: string[] = [];
    go("/portal", { "/api/portal/me": json({ detail: "no" }, 401), "POST /api/portal/login-link": json({ detail: "If that address has portal access, a sign-in link is on its way. It works once." }, 202) }, calls);
    fireEvent.change(await screen.findByLabelText("Email address"), { target: { value: "who@example.org" } });
    fireEvent.click(screen.getByRole("button", { name: /email me a link/i }));
    expect(await screen.findByRole("status")).toHaveTextContent("If that address has portal access");
    expect(calls.some((c) => c.startsWith("POST /api/portal/login-link") && c.includes("who@example.org"))).toBe(true);
    expect(calls.some((c) => c.includes("/api/auth/me"))).toBe(false); // never touches the staff session
  });

  it("redeems the link from the URL fragment and removes it from the address bar", async () => {
    window.location.hash = "#token=abc123abc123abc123abc123abc123";
    const calls: string[] = [];
    go("/portal/verify", { "POST /api/portal/verify": json(me()), "/api/portal/me": json(me()), "/api/portal/tickets": json([]) }, calls);
    await waitFor(() => expect(calls.some((c) => c.startsWith("POST /api/portal/verify") && c.includes("abc123abc123abc123abc123abc123"))).toBe(true));
    expect(window.location.hash).toBe("");
    expect(await screen.findByText(/Pat Payer/)).toBeInTheDocument();
  });

  it("says when a link cannot be used", async () => {
    window.location.hash = "#token=zzzzzzzzzzzzzzzzzzzzzzzzzzzzzz";
    go("/portal/verify", { "POST /api/portal/verify": json({ detail: "This link has expired or was already used" }, 401) });
    expect(await screen.findByText("This link cannot be used")).toBeInTheDocument();
  });

  it("shows tickets, and hides Invoices from contacts who are not billing contacts", async () => {
    go("/portal/tickets", { "/api/portal/me": json(me()), "/api/portal/tickets": json([ticket]) });
    expect(await screen.findByText(/VPN slow/)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Invoices" })).toBeNull();
  });

  it("shows invoices to billing contacts with overdue status", async () => {
    const inv = { id: 5, number: "INV-2026-0001", invoice_date: "2026-08-01", due_date: "2026-08-31", total_cents: 32475, paid_cents: 0, balance_cents: 32475, status: "unpaid", is_overdue: true, days_past_due: 30 };
    go("/portal/invoices", { "/api/portal/me": json(me({ can_see_billing: true })), "/api/portal/invoices": json([inv]), "/api/portal/tickets": json([]) });
    expect(await screen.findByText("INV-2026-0001")).toBeInTheDocument();
    expect(screen.getByText("30 days overdue")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /download account statement/i })).toHaveAttribute("href", "/api/portal/statement/pdf");
  });

  it("sends a reply on a ticket", async () => {
    const detail = { ...ticket, description: "It is slow", notes: [{ id: 1, author: "Sam Tech", from_you: false, from_support: true, body: "Looking now", created_at: "2026-09-30T13:00:00Z" }] };
    const calls: string[] = [];
    go("/portal/tickets/3", { "/api/portal/me": json(me()), "/api/portal/tickets/3": json(detail), "POST /api/portal/tickets/3/reply": json(detail, 201), "/api/portal/tickets": json([ticket]) }, calls);
    expect(await screen.findByText("Looking now")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Add a reply"), { target: { value: "Thanks!" } });
    fireEvent.click(screen.getByRole("button", { name: /send reply/i }));
    await waitFor(() => expect(calls.some((c) => c.startsWith("POST /api/portal/tickets/3/reply") && c.includes("Thanks!"))).toBe(true));
  });
});
