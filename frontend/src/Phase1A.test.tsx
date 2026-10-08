import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { fillCanned } from "./pages/TicketDetail";

const json = (body: unknown, status = 200) => () => new Response(JSON.stringify(body), { status });
const me = { id: 1, email: "u@example.com", display_name: "Una User", role: "tech", permissions: ["org:read", "user:read", "ticket:read", "ticket:write"] };
const ticket = (id: number, over = {}) => ({
  id, number: 10000 + id, organization_id: 1, organization_name: "Acme", contact_id: null, contact_name: null,
  site_id: null, queue_id: 1, queue_name: "Support", category_id: null, category_name: null,
  priority_id: 3, priority_name: "Normal", priority_rank: 3, status: "open", assignee_id: null,
  assignee_name: null, subject: `Subject ${id}`, description: null, source: "ui", requester_email: null,
  needs_triage: false, sla_state: "ok", sla_first_response_due: null, sla_resolution_due: null,
  first_responded_at: null, created_at: "2026-09-30T12:00:00Z", updated_at: "2026-09-30T12:00:00Z", ...over,
});
const base: Record<string, () => Response> = {
  "/api/auth/me": json(me),
  "/api/queues": json([{ id: 1, name: "Support", archived_at: null, is_default: true }]),
  "/api/categories": json([]),
  "/api/priorities": json([{ id: 3, name: "Normal", rank: 3, archived_at: null, is_default: true, first_response_minutes: 1, resolution_minutes: 1 }]),
  "/api/work-types": json([]),
  "/api/users": json([]),
  "/api/settings": json({}),
  "/api/organizations?limit=200&include_archived=false&q=": json({ items: [], total: 0, limit: 200, offset: 0 }),
};

function run(path: string, handlers: Record<string, (init?: RequestInit) => Response>, calls: string[] = []) {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      calls.push(`${init?.method ?? "GET"} ${url}`);
      const exact = handlers[url];
      const prefix = Object.keys(handlers).find((k) => k.endsWith("*") && url.startsWith(k.slice(0, -1)));
      const h = exact ?? (prefix ? handlers[prefix] : undefined);
      return Promise.resolve(h?.(init) ?? new Response("{}", { status: 404 }));
    }),
  );
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("fillCanned", () => {
  it("fills known placeholders and leaves unknown ones visible", () => {
    expect(fillCanned("Hi {{contact_name}}, #{{ ticket_number }} {{oops}}", { contact_name: "Pat", ticket_number: "7" })).toBe("Hi Pat, #7 {{oops}}");
  });
});

describe("ticket list", () => {
  it("selects tickets and applies a bulk change", async () => {
    const calls: string[] = [];
    const bodies: string[] = [];
    run(
      "/tickets",
      {
        ...base,
        "/api/tickets/bulk": (init) => { bodies.push(String(init?.body)); return new Response(JSON.stringify({ updated: 2, failed: [] })); },
        "/api/tickets?*": json({ items: [ticket(1), ticket(2)], total: 2, limit: 50, offset: 0 }),
      },
      calls,
    );
    await screen.findByText("Subject 1");
    expect(screen.getByText("1–2 of 2")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("checkbox", { name: "Select all tickets" }));
    expect(screen.getByText("2 selected")).toBeInTheDocument();
    fireEvent.change(within(screen.getByRole("region", { name: "Bulk actions" })).getByRole("combobox", { name: "Status" }), { target: { value: "resolved" } });
    fireEvent.click(screen.getByRole("button", { name: "Apply to 2" }));
    await waitFor(() => expect(bodies).toHaveLength(1));
    expect(JSON.parse(bodies[0])).toEqual({ ticket_ids: [1, 2], changes: { status: "resolved" } });
  });

  it("asks the server to sort when a header is clicked", async () => {
    const calls: string[] = [];
    run("/tickets", { ...base, "/api/tickets?*": json({ items: [ticket(1)], total: 1, limit: 50, offset: 0 }) }, calls);
    await screen.findByText("Subject 1");
    fireEvent.click(screen.getByRole("button", { name: "Priority" }));
    await waitFor(() => expect(calls.some((c) => c.includes("sort=priority") && c.includes("descending=false"))).toBe(true));
  });
});

describe("search page", () => {
  it("groups results by kind", async () => {
    run("/search?q=acme", {
      ...base,
      "/api/search?q=acme": json({ q: "acme", hits: [
        { kind: "ticket", id: 1, title: "#10001 Acme printer", subtitle: "open", organization_id: 1 },
        { kind: "organization", id: 1, title: "Acme Corp", subtitle: null, organization_id: 1 },
      ] }),
    });
    expect(await screen.findByRole("link", { name: "#10001 Acme printer" })).toHaveAttribute("href", "/tickets/1");
    expect(screen.getByRole("link", { name: "Acme Corp" })).toHaveAttribute("href", "/organizations/1");
    expect(screen.getByRole("heading", { name: "Clients" })).toBeInTheDocument();
  });
});

describe("settings: holidays and email automation (slice B)", () => {
  const admin = { ...me, role: "admin", permissions: [...me.permissions, "config:manage"] };
  const settings = {
    timezone: "America/Chicago", business_days: [0, 1, 2, 3, 4], business_start_minute: 480, business_end_minute: 1020,
    billing_increment_minutes: 15, sla_at_risk_percent: 25, portal_enabled: false, auto_ack_enabled: false,
    auto_ack_subject: "[#{ticket_number}] Hi", auto_ack_body: "Body", escalation_email: null, escalation_bump_priority: false,
  };
  it("lists holidays and adds a closed day", async () => {
    const bodies: string[] = [];
    run("/settings", {
      ...base,
      "/api/auth/me": json(admin),
      "/api/settings": json(settings),
      "/api/mail/status": json({ configured: false }),
      "/api/holidays": (init) => {
        if (init?.method === "POST") { bodies.push(String(init.body)); return new Response("{}", { status: 201 }); }
        return new Response(JSON.stringify([{ id: 1, on_date: "2026-12-25", name: "Christmas", open_minute: null, close_minute: null }]));
      },
    });
    expect(await screen.findByText("Christmas", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("closed")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Date"), { target: { value: "2026-07-04" } });
    const form = screen.getByRole("button", { name: "Add holiday" }).closest("form")!;
    fireEvent.change(within(form).getByLabelText("Name"), { target: { value: "Independence Day" } });
    fireEvent.click(screen.getByRole("button", { name: "Add holiday" }));
    await waitFor(() => expect(bodies).toHaveLength(1));
    expect(JSON.parse(bodies[0])).toEqual({ on_date: "2026-07-04", name: "Independence Day", open_minute: null, close_minute: null });
  });
});
