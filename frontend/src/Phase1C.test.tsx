import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";

const json = (body: unknown, status = 200) => () => new Response(JSON.stringify(body), { status });
const me = { id: 1, email: "u@example.com", display_name: "Una User", role: "tech", permissions: ["org:read", "user:read", "ticket:read", "ticket:write"] };
const ticket = {
  id: 5, number: 10005, organization_id: 1, organization_name: "Acme", contact_id: null, contact_name: null,
  site_id: null, queue_id: 1, queue_name: "Support", category_id: null, category_name: null,
  priority_id: 3, priority_name: "Normal", priority_rank: 3, status: "open", status_id: 1, status_name: "Open",
  type_id: null, type_name: null, custom_values: {}, assignee_id: null, assignee_name: null, subject: "New starter",
  description: null, source: "ui", requester_email: null, needs_triage: false, sla_state: "ok",
  sla_first_response_due: null, sla_resolution_due: null, first_responded_at: null,
  created_at: "2026-09-30T12:00:00Z", updated_at: "2026-09-30T12:00:00Z",
};
const field = (id: number, name: string, field_type: string, extra = {}) => ({
  id, name, field_type, ticket_type_id: 7, options: null, required: false, client_visible: false, position: id, archived_at: null, ...extra,
});

afterEach(() => vi.unstubAllGlobals());

describe("ticket type and custom fields", () => {
  it("shows the type's fields and saves the type with its values together", async () => {
    const bodies: string[] = [];
    const handlers: Record<string, (init?: RequestInit) => Response> = {
      "/api/auth/me": json(me),
      "/api/queues": json([{ id: 1, name: "Support", archived_at: null, is_default: true }]),
      "/api/priorities": json([{ id: 3, name: "Normal", rank: 3, archived_at: null, is_default: true, first_response_minutes: 1, resolution_minutes: 1 }]),
      "/api/ticket-statuses": json([{ id: 1, name: "Open", behavior: "open", position: 20, archived_at: null }]),
      "/api/ticket-types": json([{ id: 7, name: "New hire", archived_at: null }]),
      "/api/ticket-types/7/fields": json([
        field(1, "Start date", "date", { required: true }),
        field(2, "Laptop", "dropdown", { options: ["Dell", "HP"] }),
      ]),
      "/api/tickets/5": (init) => {
        if (init?.method === "PATCH") { bodies.push(String(init.body)); return new Response(JSON.stringify(ticket)); }
        return new Response(JSON.stringify(ticket));
      },
      "/api/tickets/5/notes": json([]),
    };
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init?: RequestInit) => Promise.resolve(handlers[url]?.(init) ?? new Response("[]", { status: 200 }))),
    );
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={["/tickets/5"]}><App /></MemoryRouter>
      </QueryClientProvider>,
    );
    const type = await screen.findByLabelText("Type");
    fireEvent.change(type, { target: { value: "7" } });
    const date = await screen.findByLabelText("Start date *");
    fireEvent.change(date, { target: { value: "2026-11-02" } });
    fireEvent.change(screen.getByLabelText("Laptop"), { target: { value: "HP" } });
    fireEvent.click(screen.getByRole("button", { name: "Save type and fields" }));
    await waitFor(() => expect(bodies).toHaveLength(1));
    expect(JSON.parse(bodies[0])).toEqual({ type_id: 7, custom_values: { "1": "2026-11-02", "2": "HP" } });
  });
});

describe("linked tickets", () => {
  it("lists links, adds one by number, and closes as a duplicate", async () => {
    const posts: string[] = [];
    const handlers: Record<string, (init?: RequestInit) => Response> = {
      "/api/auth/me": json(me),
      "/api/tickets/5": json(ticket),
      "/api/tickets/5/links": (init) => {
        if (init?.method === "POST") { posts.push(`links ${init.body}`); return new Response("[]", { status: 201 }); }
        return new Response(JSON.stringify([{ id: 3, relation: "parent", ticket_id: 9, number: 10009, subject: "Big job", status: "open", status_name: "Open" }]));
      },
      "/api/tickets/5/close-as-duplicate": (init) => { posts.push(`dup ${init?.body}`); return new Response(JSON.stringify(ticket)); },
    };
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init?: RequestInit) => Promise.resolve(handlers[url]?.(init) ?? new Response("[]", { status: 200 }))),
    );
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={["/tickets/5"]}><App /></MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByText("#10009 Big job")).toBeInTheDocument();
    expect(screen.getByText("Parent")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("This ticket is"), { target: { value: "duplicate_of" } });
    fireEvent.change(screen.getByLabelText("Ticket number"), { target: { value: "10002" } });
    fireEvent.click(screen.getByRole("button", { name: "Link" }));
    await waitFor(() => expect(posts).toHaveLength(1));
    expect(JSON.parse(posts[0].slice(6))).toEqual({ relation: "duplicate_of", other_number: 10002 });
    fireEvent.change(screen.getByLabelText("Close as duplicate of ticket number"), { target: { value: "10003" } });
    fireEvent.click(screen.getByRole("button", { name: "Close as duplicate" }));
    await waitFor(() => expect(posts).toHaveLength(2));
    expect(JSON.parse(posts[1].slice(4))).toEqual({ original_number: 10003 });
  });
});

describe("satisfaction page", () => {
  it("preselects the rating from the link and records it only after confirmation", async () => {
    const bodies: string[] = [];
    window.location.hash = "#token=abc1234567890&rating=4";
    vi.stubGlobal(
      "fetch",
      vi.fn((_url: string, init?: RequestInit) => {
        bodies.push(String(init?.body));
        return Promise.resolve(new Response(JSON.stringify({ ticket_number: 10005 })));
      }),
    );
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={["/csat"]}><App /></MemoryRouter>
      </QueryClientProvider>,
    );
    const four = await screen.findByRole("radio", { name: /4 · Happy/ });
    expect(four).toHaveAttribute("aria-checked", "true");
    expect(bodies).toHaveLength(0); // opening the link records nothing
    fireEvent.change(screen.getByLabelText(/Anything you would like to add/), { target: { value: "Thanks" } });
    fireEvent.click(screen.getByRole("button", { name: "Send feedback" }));
    expect(await screen.findByText(/request #10005/)).toBeInTheDocument();
    expect(JSON.parse(bodies[0])).toEqual({ token: "abc1234567890", rating: 4, comment: "Thanks" });
  });
});
