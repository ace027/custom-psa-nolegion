import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Ticket } from "./api";
import TicketAppointmentsCard from "./pages/TicketAppointmentsCard";

type Handler = (url: URL, init: RequestInit) => Response | Promise<Response>;
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

const READ = ["ticket:read", "schedule:read", "user:read"];
const WRITE = [...READ, "schedule:write"];
const me = (permissions: string[]) => ({ id: 3, email: "a@example.com", display_name: "Alex Admin", role: "admin", permissions });
const user = (id: number, display_name: string, role: string) => ({ id, email: `${id}@example.com`, display_name, role, is_active: true, last_login_at: null });
const SETTINGS = { timezone: "America/Chicago", business_days: [0, 1, 2, 3, 4], business_start_minute: 480, business_end_minute: 1020 };

const ticket = (over = {}) => ({ id: 7, number: 101, subject: "Printer down", organization_id: 1, organization_name: "Acme", status: "open", ...over }) as unknown as Ticket;
const appt = (over = {}) => ({
  id: 1, organization_id: 1, organization_name: "Acme", ticket_id: 7, ticket_number: 101, ticket_subject: "Printer down",
  tech_id: 2, tech_name: "Sam Tech", starts_at: "2099-10-07T14:00:00Z", ends_at: "2099-10-07T15:00:00Z", // 09:00 in Chicago
  status: "scheduled", notes: null, client_visible: true, created_by: 3, cancelled_at: null, cancel_reason: null, conflicts: [], ...over,
});
const PAST = appt({ id: 2, starts_at: "2020-01-07T14:00:00Z", ends_at: "2020-01-07T15:00:00Z" });
const FUTURE = appt();

interface Call { method: string; path: string; search: URLSearchParams; body: unknown }

function run(perms: string[], t: Ticket, extra: Record<string, Handler> = {}) {
  const calls: Call[] = [];
  const routes: Record<string, Handler> = {
    "GET /api/auth/me": () => json(me(perms)),
    "GET /api/users": () => json([user(2, "Sam Tech", "tech"), user(3, "Alex Admin", "admin")]),
    "GET /api/settings": () => json(SETTINGS),
    "GET /api/work-types": () => json([{ id: 5, name: "Remote" }, { id: 6, name: "Onsite" }]),
    "GET /api/appointments": () => json([FUTURE, PAST]),
    "GET /api/appointments/1": () => json({ ...FUTURE, conflicts: [{ kind: "overlap", time_off_id: null, appointment_id: 9 }] }),
    "GET /api/appointments/2": () => json({ ...PAST, conflicts: [{ kind: "overlap", time_off_id: null, appointment_id: 9 }] }),
    ...extra,
  };
  vi.stubGlobal("fetch", vi.fn(async (raw: string, init: RequestInit = {}) => {
    const url = new URL(raw, "http://test");
    const method = init.method ?? "GET";
    calls.push({ method, path: url.pathname, search: url.searchParams, body: init.body ? JSON.parse(String(init.body)) : undefined });
    const h = routes[`${method} ${url.pathname}`];
    return h ? h(url, init) : json({ detail: "not found" }, 404);
  }));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <TicketAppointmentsCard ticket={t} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return calls;
}

afterEach(() => vi.unstubAllGlobals());

describe("ticket appointments card", () => {
  it("lists appointments sorted, marks conflicts on upcoming rows only, and links to the board", async () => {
    const calls = run(WRITE, ticket());
    expect(await screen.findAllByText("Sam Tech")).toHaveLength(2);
    const items = screen.getAllByRole("listitem");
    expect(items[0]).toHaveTextContent("2020"); // past first
    expect(items[1]).toHaveTextContent("2099");
    await waitFor(() => expect(within(items[1]).getByText("Has conflicts")).toBeInTheDocument());
    expect(within(items[0]).queryByText("Has conflicts")).not.toBeInTheDocument();
    expect(calls.some((c) => c.path === "/api/appointments/2")).toBe(false);
    expect(calls.find((c) => c.path === "/api/appointments")!.search.get("ticket_id")).toBe("7");
    expect(within(items[1]).getByRole("link", { name: "Open on board" })).toHaveAttribute("href", "/dispatch?view=day&date=2099-10-07");
    expect(within(items[0]).queryByRole("button", { name: "Start timer" })).not.toBeInTheDocument();
    expect(within(items[1]).getByRole("button", { name: "Start timer" })).toBeInTheDocument();
  });

  it("Book opens the booking dialog with the ticket fixed", async () => {
    run(WRITE, ticket());
    fireEvent.click(await screen.findByRole("button", { name: "Book" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByLabelText("Tech")).toBeInTheDocument();
    expect(within(dialog).queryByLabelText("Ticket")).not.toBeInTheDocument(); // no ticket search
  });

  it("hides Book on a closed ticket or one without an organization", async () => {
    run(WRITE, ticket({ status: "closed" }));
    await screen.findAllByText("Sam Tech");
    expect(screen.queryByRole("button", { name: "Book" })).not.toBeInTheDocument();
  });

  it("hides Book without an organization", async () => {
    run(WRITE, ticket({ organization_id: null }));
    await screen.findAllByText("Sam Tech");
    expect(screen.queryByRole("button", { name: "Book" })).not.toBeInTheDocument();
  });

  it("Start timer posts the body, and a 409 shows its detail", async () => {
    let conflict = true;
    const calls = run(WRITE, ticket(), {
      "POST /api/timer/start": () => (conflict ? json({ detail: "A timer is already running" }, 409) : json({ started_at: "2099-01-01T00:00:00Z" })),
    });
    await screen.findAllByText("Sam Tech");
    fireEvent.click(screen.getByRole("button", { name: "Start timer" }));
    await waitFor(() => expect(screen.getByLabelText("Work type")).toBeInTheDocument());
    await waitFor(() => expect(within(screen.getByLabelText("Work type")).getAllByRole("option")).toHaveLength(3));
    fireEvent.change(screen.getByLabelText("Work type"), { target: { value: "5" } });
    fireEvent.click(screen.getByRole("button", { name: "Start" }));
    expect(await screen.findByText("A timer is already running")).toBeInTheDocument();
    const post = calls.find((c) => c.method === "POST" && c.path === "/api/timer/start")!;
    expect(post.body).toEqual({ ticket_id: 7, work_type_id: 5, billable: true, note: "Appointment 2099-10-07" });

    conflict = false;
    fireEvent.click(screen.getByRole("button", { name: "Start" }));
    await waitFor(() => expect(screen.queryByLabelText("Work type")).not.toBeInTheDocument());
  });

  it("a read-only user sees the list but no Book or Start timer", async () => {
    run(READ, ticket());
    expect(await screen.findAllByText("Sam Tech")).toHaveLength(2);
    expect(screen.queryByRole("button", { name: "Book" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Start timer" })).not.toBeInTheDocument();
  });
});
