import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import Dispatch from "./pages/Dispatch";
import { OutlookSyncCard } from "./pages/Settings";

type Handler = (url: URL, init: RequestInit) => Response | Promise<Response>;
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

const READ = ["org:read", "user:read", "ticket:read", "schedule:read"];
const WRITE = [...READ, "ticket:write", "schedule:write"];
const me = (permissions: string[], role = "admin") => ({ id: 3, email: "a@example.com", display_name: "Alex Admin", role, permissions });
const user = (id: number, display_name: string, role: string) => ({ id, email: `${id}@example.com`, display_name, role, is_active: true, last_login_at: null });
const USERS = [user(2, "Sam Tech", "tech"), user(3, "Alex Admin", "admin")];
const SETTINGS = { timezone: "America/Chicago", business_days: [0, 1, 2, 3, 4], business_start_minute: 480, business_end_minute: 1020 };

const appt = (over = {}) => ({
  id: 1, organization_id: 1, organization_name: "Acme", ticket_id: 7, ticket_number: 101, ticket_subject: "Printer down",
  tech_id: 2, tech_name: "Sam Tech", starts_at: "2026-10-07T14:00:00Z", ends_at: "2026-10-07T15:00:00Z",
  status: "scheduled", notes: null, client_visible: true, created_by: 3, cancelled_at: null, cancel_reason: null,
  conflicts: [], sync: { state: "failed", last_error: "403 mailbox outside the scope" }, ...over,
});
const minutesAgo = (m: number) => new Date(Date.now() - m * 60_000).toISOString();
const avail = (user_id: number, fetched: string | null) => ({
  user_id, timezone: "America/Chicago", working: [{ starts_at: "2026-10-07T13:00:00Z", ends_at: "2026-10-07T22:00:00Z" }],
  time_off: [], time_off_pending: [], appointments: [], free: [],
  outlook_busy: [{ starts_at: "2026-10-07T17:00:00Z", ends_at: "2026-10-07T18:00:00Z", status: "busy" }], outlook_fetched_at: fetched,
});
const status = (over = {}) => ({
  enabled: true, pending: 0, failed: 1, busy_fetched_at: minutesAgo(2), busy_errors: 0,
  failures: [{ appointment_id: 1, ticket_id: 7, tech_id: 2, last_error: "403 mailbox outside the scope", updated_at: minutesAgo(1) }], ...over,
});

interface Call { method: string; path: string }

function setup(ui: React.ReactElement, perms: string[], routes: Record<string, Handler>, role = "admin") {
  const calls: Call[] = [];
  const all: Record<string, Handler> = {
    "GET /api/auth/me": () => json(me(perms, role)),
    "GET /api/users": () => json(USERS),
    "GET /api/settings": () => json(SETTINGS),
    ...routes,
  };
  vi.stubGlobal("fetch", vi.fn(async (raw: string, init: RequestInit = {}) => {
    const url = new URL(raw, "http://test");
    const method = init.method ?? "GET";
    calls.push({ method, path: url.pathname });
    const h = all[`${method} ${url.pathname}`];
    return h ? h(url, init) : json({ detail: "not found" }, 404);
  }));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/dispatch?date=2026-10-07"]}>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
  return calls;
}
const board = (perms: string[], over: { status?: Handler; fetched?: string | null; retry?: Handler } = {}) => {
  const state = { failed: true };
  const calls = setup(<Dispatch />, perms, {
    "GET /api/appointments": () => json([appt(state.failed ? {} : { sync: { state: "pending", last_error: null } })]),
    "GET /api/availability": () => json([avail(2, over.fetched === undefined ? minutesAgo(3) : over.fetched), avail(3, over.fetched === undefined ? minutesAgo(3) : over.fetched)]),
    "GET /api/calendar-sync/status": over.status ?? (() => json(state.failed ? status() : status({ failed: 0, pending: 1, failures: [] }))),
    "POST /api/appointments/1/sync/retry": over.retry ?? (() => { state.failed = false; return json(appt({ sync: { state: "pending", last_error: null } })); }),
  });
  return calls;
};

afterEach(() => vi.unstubAllGlobals());

describe("Outlook sync on the board", () => {
  it("marks a failed appointment with accessible text and shows the failure chip", async () => {
    board(WRITE);
    const block = (await screen.findByText("#101 Acme")).closest(".rbc-event") as HTMLElement;
    expect(within(block).getByText("Outlook sync failed")).toHaveClass("sr-only");
    expect(await screen.findByRole("button", { name: "1 Outlook sync failure" })).toBeInTheDocument();
  });

  it("shows nothing about Outlook sync when it is off", async () => {
    board(WRITE, { status: () => json(status({ enabled: false, failed: 0, failures: [] })), fetched: null });
    await screen.findByText("#101 Acme");
    await waitFor(() => expect(screen.getByText("Outlook busy")).toBeInTheDocument()); // legend entry stays
    expect(screen.queryByTestId("outlook-caption")).not.toBeInTheDocument();
    expect(screen.queryByText(/Outlook sync failure/)).not.toBeInTheDocument();
  });

  it("retries from the dialog, calls the API and refreshes", async () => {
    const calls = board(WRITE);
    fireEvent.click((await screen.findByText("#101 Acme")).closest(".rbc-event") as HTMLElement);
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Outlook sync failed: 403 mailbox outside the scope")).toBeInTheDocument();
    const before = calls.filter((c) => c.path === "/api/calendar-sync/status").length;
    fireEvent.click(within(dialog).getByRole("button", { name: "Retry Outlook sync" }));
    expect(await within(dialog).findByText("Waiting to sync")).toBeInTheDocument();
    expect(calls.some((c) => c.method === "POST" && c.path === "/api/appointments/1/sync/retry")).toBe(true);
    await waitFor(() => expect(calls.filter((c) => c.path === "/api/calendar-sync/status").length).toBeGreaterThan(before));
    await waitFor(() => expect(screen.queryByRole("button", { name: /Outlook sync failure/ })).not.toBeInTheDocument());
  });

  it("explains a 409 from a retry that already happened", async () => {
    board(WRITE, { retry: () => json({ detail: "not failed" }, 409) });
    fireEvent.click((await screen.findByText("#101 Acme")).closest(".rbc-event") as HTMLElement);
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Retry Outlook sync" }));
    expect(await within(dialog).findByText("This sync was already retried; it is no longer failed.")).toBeInTheDocument();
  });

  it("retries from the failure list, and read-only users get no retry button", async () => {
    const calls = board(WRITE);
    fireEvent.click(await screen.findByRole("button", { name: "1 Outlook sync failure" }));
    const list = document.getElementById("sync-failures")!;
    expect(within(list).getByRole("link", { name: "Ticket #7" })).toHaveAttribute("href", "/tickets/7");
    expect(within(list).getByText("403 mailbox outside the scope")).toBeInTheDocument();
    fireEvent.click(within(list).getByRole("button", { name: /Retry/ }));
    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.path === "/api/appointments/1/sync/retry")).toBe(true));
  });

  it("hides retry without schedule:write", async () => {
    board(READ);
    fireEvent.click(await screen.findByRole("button", { name: "1 Outlook sync failure" }));
    expect(within(document.getElementById("sync-failures")!).queryByRole("button")).not.toBeInTheDocument();
  });

  it("shows the stale caption for an old fetch, the fresh caption otherwise, and not-loaded for null", async () => {
    board(WRITE, { fetched: minutesAgo(40) });
    expect(await screen.findByText(/Outlook busy may be out of date \(updated 40 min ago\)/)).toBeInTheDocument();
  });
  it("shows the fresh caption", async () => {
    board(WRITE, { fetched: minutesAgo(3) });
    expect(await screen.findByText("Outlook busy updated 3 min ago")).toBeInTheDocument();
  });
  it("shows not loaded yet when never fetched", async () => {
    board(WRITE, { fetched: null });
    expect(await screen.findByText(/Outlook busy not loaded yet/)).toBeInTheDocument();
  });
});

describe("Outlook calendar sync card", () => {
  const card = (perms: string[], role: string, enabled = false) => {
    const patches: unknown[] = [];
    setup(<OutlookSyncCard />, perms, {
      "GET /api/calendar-sync/status": () => json(status({ enabled, failed: 2, pending: 3, failures: [] })),
      "PATCH /api/settings": (_u, init) => { patches.push(JSON.parse(String(init.body))); return json(SETTINGS); },
    }, role);
    return patches;
  };
  it("lets an admin switch it on", async () => {
    const patches = card(WRITE, "admin");
    const box = await screen.findByRole("checkbox");
    fireEvent.click(box);
    await waitFor(() => expect(patches).toEqual([{ outlook_sync_enabled: true }]));
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText(/docs\/CALENDAR_SETUP\.md/)).toBeInTheDocument();
  });
  it("hides the toggle from non-admins", async () => {
    card(WRITE, "tech");
    expect(await screen.findByText(/Only an admin can change this/)).toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  });
});
