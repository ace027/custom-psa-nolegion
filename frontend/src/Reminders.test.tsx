import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";

const json = (body: unknown, status = 200) => () => new Response(JSON.stringify(body), { status });
const me = (role: string, permissions: string[]) => ({ id: 1, email: "u@example.com", display_name: "Una User", role, permissions });
const READ = ["org:read", "user:read", "ticket:read", "billing:read"];
const BILL = [...READ, "billing:write", "billing:finalize", "charge:write", "payment:write"];

const notice = (over = {}) => ({
  id: 7, kind: "reminder", organization_id: 1, organization_name: "Acme Corp", status: "pending", manual: false,
  stage_name: "Friendly reminder", subject: "Past due invoice", body_text: "Hello Pat,\n\nPlease pay.", to_emails: ["pat@acme.com"],
  blocked_reason: null, statement_id: null, stale: false, total_due_cents: 10000, created_at: "2026-09-30T12:00:00Z",
  decided_at: null, dismiss_reason: null, email_status: null,
  invoices: [{ invoice_id: 1, number: "INV-2026-0001", due_date: "2026-09-01", balance_cents: 10000, days_past_due: 29, new_stage: true }], ...over,
});
const page = (items: unknown[]) => ({ items, total: items.length, limit: 200, offset: 0 });
const PENDING = "/api/billing-notices?status=pending&limit=200";

function go(path: string, handlers: Record<string, () => Response>, calls: string[] = []) {
  vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => {
    const key = init?.method && init.method !== "GET" ? `${init.method} ${url}` : url;
    calls.push(key);
    return Promise.resolve(handlers[key]?.() ?? new Response("{}", { status: 404 }));
  }));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><MemoryRouter initialEntries={[path]}><App /></MemoryRouter></QueryClientProvider>);
}
afterEach(() => vi.unstubAllGlobals());

describe("reminder review queue", () => {
  it("shows what will be sent, and sends only when approved", async () => {
    const calls: string[] = [];
    go("/billing/reminders", {
      "/api/auth/me": json(me("billing", BILL)), "/api/receivables": json({ as_of: "2026-09-30", rows: [], totals: {} }),
      [PENDING]: json(page([notice()])), "POST /api/billing-notices/7/send": json(notice({ status: "sent" })),
    }, calls);
    expect(await screen.findByText("Acme Corp")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Past due invoice")).toBeInTheDocument();
    expect(screen.getByText(/To: pat@acme.com/)).toBeInTheDocument();
    expect(calls.some((c) => c.startsWith("POST"))).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: /approve & send/i }));
    await waitFor(() => expect(calls).toContain("POST /api/billing-notices/7/send"));
  });

  it("blocks sending when there is no recipient or the numbers changed", async () => {
    go("/billing/reminders", {
      "/api/auth/me": json(me("billing", BILL)), "/api/receivables": json({ as_of: "2026-09-30", rows: [], totals: {} }),
      [PENDING]: json(page([notice({ blocked_reason: "No billing or primary contact has an email address", to_emails: [] }), notice({ id: 8, organization_name: "Beta LLC", stale: true })])),
    });
    expect(await screen.findByText(/No billing or primary contact/)).toBeInTheDocument();
    expect(screen.getByText(/Balances have changed/)).toBeInTheDocument();
    for (const b of screen.getAllByRole("button", { name: /approve & send/i })) expect(b).toBeDisabled();
  });

  it("needs a reason to dismiss", async () => {
    const calls: string[] = [];
    go("/billing/reminders", {
      "/api/auth/me": json(me("billing", BILL)), "/api/receivables": json({ as_of: "2026-09-30", rows: [], totals: {} }),
      [PENDING]: json(page([notice()])), "POST /api/billing-notices/7/dismiss": json(notice({ status: "dismissed" })),
    }, calls);
    fireEvent.click(await screen.findByRole("button", { name: "Dismiss" }));
    expect(screen.getByRole("button", { name: /confirm dismiss/i })).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Dismiss reason"), { target: { value: "spoke by phone" } });
    fireEvent.click(screen.getByRole("button", { name: /confirm dismiss/i }));
    await waitFor(() => expect(calls).toContain("POST /api/billing-notices/7/dismiss"));
  });

  it("is read-only for people who cannot write billing", async () => {
    go("/billing/reminders", {
      "/api/auth/me": json(me("tech", READ)), "/api/receivables": json({ as_of: "2026-09-30", rows: [], totals: {} }),
      [PENDING]: json(page([notice()])),
    });
    expect(await screen.findByText("Acme Corp")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /approve & send/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /prepare reminders/i })).toBeNull();
  });

  it("shows the review count on the Billing tab", async () => {
    go("/billing/reminders", {
      "/api/auth/me": json(me("billing", BILL)), "/api/receivables": json({ as_of: "2026-09-30", rows: [], totals: {} }),
      [PENDING]: json(page([notice(), notice({ id: 8 })])),
    });
    expect(await screen.findByText("2 to review")).toBeInTheDocument();
  });
});
