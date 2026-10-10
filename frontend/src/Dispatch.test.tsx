import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import Dispatch from "./pages/Dispatch";

type Handler = (url: URL, init: RequestInit) => Response | Promise<Response>;
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

const READ = ["org:read", "user:read", "ticket:read", "schedule:read"];
const WRITE = [...READ, "ticket:write", "schedule:write"];
const me = (permissions: string[]) => ({ id: 3, email: "a@example.com", display_name: "Alex Admin", role: "admin", permissions });
const user = (id: number, display_name: string, role: string) => ({ id, email: `${id}@example.com`, display_name, role, is_active: true, last_login_at: null });
const USERS = [user(2, "Sam Tech", "tech"), user(3, "Alex Admin", "admin"), user(4, "Bill Billing", "billing")];
const SETTINGS = { timezone: "America/Chicago", business_days: [0, 1, 2, 3, 4], business_start_minute: 480, business_end_minute: 1020 };

const appt = (over = {}) => ({
  id: 1, organization_id: 1, organization_name: "Acme", ticket_id: 7, ticket_number: 101, ticket_subject: "Printer down",
  tech_id: 2, tech_name: "Sam Tech", starts_at: "2026-10-07T14:00:00Z", ends_at: "2026-10-07T15:00:00Z", // 09:00-10:00 in Chicago
  status: "scheduled", notes: null, client_visible: true, created_by: 3, cancelled_at: null, cancel_reason: null,
  conflicts: [{ kind: "overlap", time_off_id: null, appointment_id: 2 }], ...over,
});
const APPTS = [
  appt(),
  appt({ id: 2, ticket_id: 8, ticket_number: 102, organization_name: "Globex", tech_id: 3, tech_name: "Alex Admin", starts_at: "2026-10-07T16:00:00Z", ends_at: "2026-10-07T17:00:00Z", conflicts: [] }),
  appt({ id: 3, ticket_number: 103, organization_name: "Gone", status: "cancelled", conflicts: [] }),
];
const avail = (user_id: number, timezone: string) => ({ user_id, timezone, working: [{ starts_at: "2026-10-07T13:00:00Z", ends_at: "2026-10-07T22:00:00Z" }], time_off: [], time_off_pending: [], appointments: [], free: [] });
const AVAIL = [avail(2, "America/New_York"), avail(3, "America/Chicago")];

interface Call { method: string; path: string; search: URLSearchParams; body: unknown }

function run(perms: string[], entry: string, extra: Record<string, Handler> = {}) {
  const calls: Call[] = [];
  const routes: Record<string, Handler> = {
    "GET /api/auth/me": () => json(me(perms)),
    "GET /api/users": () => json(USERS),
    "GET /api/settings": () => json(SETTINGS),
    "GET /api/appointments": () => json(APPTS),
    "GET /api/availability": () => json(AVAIL),
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
      <MemoryRouter initialEntries={[entry]}>
        <Dispatch />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return calls;
}
const eventEl = async (title: string) => (await screen.findByText(title)).closest(".rbc-event") as HTMLElement;

afterEach(() => vi.unstubAllGlobals());

describe("dispatch board", () => {
  it("day view shows a column per bookable tech, the events and the org zone", async () => {
    const calls = run(WRITE, "/dispatch?date=2026-10-07");
    expect(await screen.findByText("#101 Acme")).toBeInTheDocument();
    expect(screen.getByText("#102 Globex")).toBeInTheDocument();
    expect(screen.getByText("Sam Tech")).toBeInTheDocument();
    expect(screen.getByText("Alex Admin")).toBeInTheDocument();
    expect(screen.queryByText("Bill Billing")).not.toBeInTheDocument();
    expect(screen.queryByText("#103 Gone")).not.toBeInTheDocument(); // cancelled
    expect(screen.getByText("Times in America/Chicago")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "New booking" })).toBeInTheDocument();
    const list = calls.find((c) => c.path === "/api/appointments")!;
    expect(list.search.get("from")).toBe("2026-10-07T05:00:00.000Z");
    expect(list.search.get("to")).toBe("2026-10-08T05:00:00.000Z");
    expect(list.search.get("with_conflicts")).toBe("true");
  });

  it("is view only without schedule:write", async () => {
    run(READ, "/dispatch?date=2026-10-07");
    expect(await screen.findByText("#101 Acme")).toBeInTheDocument();
    expect(screen.getByText("View only")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "New booking" })).not.toBeInTheDocument();
    fireEvent.click(await eventEl("#101 Acme"));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByLabelText("Start")).toBeDisabled();
    expect(within(dialog).queryByRole("button", { name: "Save" })).not.toBeInTheDocument();
    expect(within(dialog).queryByRole("button", { name: "Cancel appointment" })).not.toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Close" })).toBeInTheDocument();
  });

  it("shows an empty state with no techs", async () => {
    run(WRITE, "/dispatch?date=2026-10-07", { "GET /api/users": () => json([user(4, "Bill Billing", "billing")]) });
    expect(await screen.findByText("No active admins or techs")).toBeInTheDocument();
  });

  it("marks conflicts on the block and shows tech-local time when zones differ", async () => {
    run(WRITE, "/dispatch?date=2026-10-07");
    const el = await eventEl("#101 Acme");
    expect(within(el).getByLabelText("Has conflicts")).toBeInTheDocument();
    expect(el).toHaveClass("has-conflict");
    await waitFor(() => expect(el.getAttribute("title")).toContain("Tech local: 10:00–11:00"));
    expect(el.getAttribute("title")).toContain("Overlaps another appointment");
    const other = await eventEl("#102 Globex");
    expect(within(other).queryByLabelText("Has conflicts")).not.toBeInTheDocument();
    expect(other.getAttribute("title")).not.toContain("Tech local");
  });

  it("edit dialog saves only the changed field, then Undo sends the reverse PATCH", async () => {
    const calls = run(WRITE, "/dispatch?date=2026-10-07", {
      "PATCH /api/appointments/1": (_u, init) => {
        const body = JSON.parse(String(init.body));
        return json(appt({ ...body, starts_at: body.starts_at, conflicts: body.tech_id ? [] : [{ kind: "outside_hours", time_off_id: null, appointment_id: null }] }));
      },
    });
    fireEvent.click(await eventEl("#101 Acme"));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("link", { name: "#101 Printer down" })).toHaveAttribute("href", "/tickets/7");
    expect(within(dialog).getByText("Overlaps another appointment")).toBeInTheDocument();
    expect(within(dialog).getByLabelText("Start")).toHaveValue("09:00");
    fireEvent.change(within(dialog).getByLabelText("Start"), { target: { value: "09:30" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));

    const status = screen.getByRole("status");
    await waitFor(() => expect(status).toHaveTextContent(/Rescheduled to Wed 09:30, resized to 30m · Outside working hours/));
    const patches = calls.filter((c) => c.method === "PATCH");
    expect(patches).toHaveLength(1);
    expect(patches[0].body).toEqual({ starts_at: "2026-10-07T14:30:00.000Z" });

    fireEvent.click(within(status).getByRole("button", { name: "Undo" }));
    await waitFor(() => expect(status).toHaveTextContent("Change undone"));
    const undo = calls.filter((c) => c.method === "PATCH")[1];
    expect(undo.body).toEqual({ tech_id: 2, starts_at: "2026-10-07T14:00:00.000Z", ends_at: "2026-10-07T15:00:00.000Z" });
  });

  it("sends nothing when the edit changes nothing", async () => {
    const calls = run(WRITE, "/dispatch?date=2026-10-07");
    fireEvent.click(await eventEl("#101 Acme"));
    fireEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(calls.some((c) => c.method === "PATCH")).toBe(false);
  });

  it("rolls back and shows the detail when a PATCH fails with 409", async () => {
    let failed = false;
    run(WRITE, "/dispatch?date=2026-10-07", {
      // After the failure, the refetch never answers, so only the rollback can restore the block.
      "GET /api/appointments": () => (failed ? new Promise<Response>(() => {}) : json(APPTS)),
      "PATCH /api/appointments/1": () => {
        failed = true;
        return json({ detail: "Only scheduled appointments can be changed" }, 409);
      },
    });
    const before = await eventEl("#101 Acme");
    expect(before).toHaveTextContent("09:00–10:00");
    fireEvent.click(before);
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText("Start"), { target: { value: "11:00" } });
    fireEvent.change(within(dialog).getByLabelText("End"), { target: { value: "12:00" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Only scheduled appointments can be changed");
    expect(await eventEl("#101 Acme")).toHaveTextContent("09:00–10:00");
  });

  it("books a ticket from the New booking dialog with UTC times", async () => {
    const calls = run(WRITE, "/dispatch?date=2026-10-07", {
      "GET /api/tickets": (u) => json({ items: u.searchParams.get("q") === "print" ? [{ id: 7, number: 10007, subject: "Printer down", organization_name: "Acme" }] : [], total: 1, limit: 10, offset: 0 }),
      "POST /api/appointments": (_u, init) => json(appt({ id: 9, ...JSON.parse(String(init.body)), conflicts: [{ kind: "outside_hours", time_off_id: null, appointment_id: null }] }), 201),
    });
    fireEvent.click(await screen.findByRole("button", { name: "New booking" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByLabelText("Ticket")).toHaveFocus();
    fireEvent.change(within(dialog).getByLabelText("Ticket"), { target: { value: "print" } });
    fireEvent.click(await within(dialog).findByRole("button", { name: "#10007 Printer down (Acme)" }));
    fireEvent.change(within(dialog).getByLabelText("Tech"), { target: { value: "2" } });
    fireEvent.change(within(dialog).getByLabelText("Date"), { target: { value: "2026-10-08" } });
    fireEvent.change(within(dialog).getByLabelText("Start"), { target: { value: "13:00" } });
    fireEvent.change(within(dialog).getByLabelText("End"), { target: { value: "14:30" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Book" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    const post = calls.find((c) => c.method === "POST")!;
    expect(post.body).toEqual({ ticket_id: 7, tech_id: 2, starts_at: "2026-10-08T18:00:00.000Z", ends_at: "2026-10-08T19:30:00.000Z", notes: null, client_visible: true });
    expect(screen.getByRole("status")).toHaveTextContent("Outside working hours");
  });

  it("closes the booking dialog with Escape", async () => {
    run(WRITE, "/dispatch?date=2026-10-07");
    fireEvent.click(await screen.findByRole("button", { name: "New booking" }));
    fireEvent.keyDown(await screen.findByRole("dialog"), { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("week view renders in the selected tech's zone from their schedule", async () => {
    const calls = run(WRITE, "/dispatch?view=week&date=2026-10-07&tech=2", {
      "GET /api/users/2/schedule": () => json({ user_id: 2, timezone: "America/New_York", timezone_override: "America/New_York", uses_default_hours: true, work_hours: [] }),
    });
    expect(await screen.findByText("Times in America/New_York")).toBeInTheDocument();
    expect(await screen.findByText("#101 Acme")).toBeInTheDocument();
    expect(screen.queryByText("#102 Globex")).not.toBeInTheDocument(); // another tech's
    const list = calls.find((c) => c.path === "/api/appointments")!;
    expect(list.search.get("from")).toBe("2026-10-05T04:00:00.000Z"); // Monday 00:00 New York
    expect(list.search.get("to")).toBe("2026-10-12T04:00:00.000Z");
    expect(list.search.get("tech_id")).toBe("2");
  });

  it("week view falls back to the availability zone when the schedule is forbidden", async () => {
    run(WRITE, "/dispatch?view=week&date=2026-10-07&tech=2", {
      "GET /api/users/2/schedule": () => json({ detail: "Forbidden" }, 403),
    });
    expect(await screen.findByText("Times in America/New_York")).toBeInTheDocument();
  });
});
