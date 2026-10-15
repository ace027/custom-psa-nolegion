import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import OnCallWidget from "./OnCallWidget";
import OnCall from "./pages/OnCall";
import { AppointmentEmailsCard } from "./pages/Settings";
import { BookingDialog } from "./scheduling/BookingDialog";
import { EditDialog } from "./scheduling/EditDialog";
import type { Appointment } from "./scheduling/api";

type Handler = (url: URL, init: RequestInit) => Response | Promise<Response>;
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

const READ = ["schedule:read"];
const WRITE = ["schedule:read", "schedule:write", "config:manage"];
const me = (permissions: string[]) => ({ id: 3, email: "a@example.com", display_name: "Alex Admin", role: "admin", permissions });
const user = (id: number, display_name: string, role = "tech") => ({ id, email: `${id}@example.com`, display_name, role, is_active: true, last_login_at: null });
const USERS = [user(2, "Sam Tech"), user(3, "Alex Admin", "admin")];
const SETTINGS = { timezone: "America/Chicago", appointment_emails_enabled: false };
const ROTATION = {
  id: 4, name: "Weekly", handoff_weekday: 0, handoff_time: "09:00:00", anchor_date: "2030-01-07", active: true,
  members: [{ user_id: 2, name: "Sam Tech", position: 0 }, { user_id: 3, name: "Alex Admin", position: 1 }],
};

interface Call { method: string; path: string; body: unknown }

function setup(ui: React.ReactElement, perms: string[], routes: Record<string, Handler>) {
  const calls: Call[] = [];
  const all: Record<string, Handler> = {
    "GET /api/auth/me": () => json(me(perms)),
    "GET /api/users": () => json(USERS),
    "GET /api/settings": () => json(SETTINGS),
    ...routes,
  };
  vi.stubGlobal("fetch", vi.fn(async (raw: string, init: RequestInit = {}) => {
    const url = new URL(raw, "http://test");
    const method = init.method ?? "GET";
    calls.push({ method, path: url.pathname, body: init.body ? JSON.parse(String(init.body)) : undefined });
    const h = all[`${method} ${url.pathname}`];
    return h ? h(url, init) : json({ detail: "not found" }, 404);
  }));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
  return calls;
}

afterEach(() => vi.unstubAllGlobals());

const appt = (over: Partial<Appointment> = {}): Appointment => ({
  id: 1, organization_id: 1, organization_name: "Acme", ticket_id: 7, ticket_number: 101, ticket_subject: "Printer down",
  tech_id: 2, tech_name: "Sam Tech", starts_at: "2030-01-07T15:00:00Z", ends_at: "2030-01-07T16:00:00Z",
  status: "scheduled", notes: null, client_visible: true, notify_client: true, created_by: 3, cancelled_at: null, cancel_reason: null,
  conflicts: [], sync: { state: "off", last_error: null },
  client_notice: { state: "pending", kind: null, send_after: "2030-01-07T14:00:00Z", sent_at: null, reason: null }, ...over,
});

describe("appointment emails setting", () => {
  it("shows the help line and patches the switch", async () => {
    const calls = setup(<AppointmentEmailsCard />, WRITE, { "PATCH /api/settings": () => json({ ...SETTINGS, appointment_emails_enabled: true }) });
    const sw = await screen.findByRole("switch", { name: "Send appointment emails" });
    expect(sw).not.toBeChecked();
    expect(screen.getByText("Email the ticket contact when a client-visible appointment is booked, moved or cancelled")).toBeInTheDocument();
    fireEvent.click(sw);
    await waitFor(() => expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({ appointment_emails_enabled: true }));
  });
});

describe("booking and edit dialogs", () => {
  it("sends notify_client false when Don't email client is ticked, and hides it for non-visible bookings", async () => {
    const calls = setup(<BookingDialog open onClose={() => undefined} zone="America/Chicago" initial={{ ticketId: 7, techId: 2, start: new Date(2030, 0, 7, 9), end: new Date(2030, 0, 7, 10) }} />, WRITE, {
      "POST /api/appointments": () => json(appt(), 201),
    });
    const box = await screen.findByLabelText("Don't email client");
    expect(box).not.toBeChecked();
    fireEvent.click(box);
    fireEvent.click(screen.getByLabelText("Visible to client"));
    expect(screen.queryByLabelText("Don't email client")).not.toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("Visible to client"));
    fireEvent.click(screen.getByRole("button", { name: "Book" }));
    await waitFor(() => expect(calls.find((c) => c.method === "POST")?.body).toMatchObject({ ticket_id: 7, client_visible: true, notify_client: false }));
  });

  const edit = (a: Appointment, canWrite = true) => {
    const onSave = vi.fn();
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <EditDialog appointment={a} zone="America/Chicago" staff={USERS.map((u) => ({ id: u.id, display_name: u.display_name, role: u.role as "tech" }))} canWrite={canWrite} onClose={() => undefined} onSave={onSave} />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    return onSave;
  };

  it("words the notice state: queued, emailed, not emailed", () => {
    edit(appt());
    expect(screen.getByTestId("notice-line")).toHaveTextContent("Email queued");
    cleanup();
    edit(appt({ client_notice: { state: "sent", kind: "booked", send_after: "2030-01-07T14:00:00Z", sent_at: "2030-01-07T15:00:00Z", reason: null } }));
    expect(screen.getByTestId("notice-line")).toHaveTextContent("Emailed booked Mon 7 Jan 09:00");
    cleanup();
    edit(appt({ client_notice: { state: "skipped", kind: null, send_after: "2030-01-07T14:00:00Z", sent_at: null, reason: "contact has no email" } }));
    expect(screen.getByTestId("notice-line")).toHaveTextContent("Not emailed: contact has no email");
  });

  it("patches notify_client when the checkbox changes, and hides it for internal appointments", () => {
    const onSave = edit(appt());
    fireEvent.click(screen.getByLabelText("Don't email client"));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(onSave).toHaveBeenCalledWith({ notify_client: false });
    cleanup();
    edit(appt({ client_visible: false, client_notice: null }));
    expect(screen.queryByLabelText("Don't email client")).not.toBeInTheDocument();
    expect(screen.queryByTestId("notice-line")).not.toBeInTheDocument();
  });
});

describe("on-call page", () => {
  const routes = (over: Record<string, Handler> = {}): Record<string, Handler> => ({
    "GET /api/oncall/rotations": () => json([ROTATION]),
    "GET /api/oncall/rotations/4/overrides": () => json([{ id: 9, rotation_id: 4, user_id: 3, user_name: "Alex Admin", starts_at: "2030-01-08T15:00:00Z", ends_at: "2030-01-09T15:00:00Z", reason: "Holiday", created_at: "2030-01-01T00:00:00Z" }]),
    "GET /api/oncall/schedule": () => json([{ rotation_id: 4, user_id: 2, user_name: "Sam Tech", starts_at: "2030-01-07T15:00:00Z", ends_at: "2030-01-14T15:00:00Z", source: "rotation" }]),
    ...over,
  });

  it("creates a rotation with ordered members", async () => {
    const calls = setup(<OnCall />, WRITE, routes({ "POST /api/oncall/rotations": () => json(ROTATION, 201) }));
    fireEvent.click(await screen.findByRole("button", { name: "New rotation" }));
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Nights" } });
    fireEvent.change(screen.getByLabelText("Handoff weekday"), { target: { value: "2" } });
    fireEvent.change(screen.getByLabelText("Anchor date"), { target: { value: "2030-01-09" } });
    for (const id of ["3", "2"]) {
      fireEvent.change(screen.getByLabelText("Add member"), { target: { value: id } });
      fireEvent.click(screen.getByRole("button", { name: "Add member" }));
    }
    fireEvent.click(screen.getByRole("button", { name: "Move Sam Tech up" }));
    fireEvent.click(screen.getByRole("button", { name: "Create rotation" }));
    await waitFor(() => expect(calls.find((c) => c.method === "POST")).toBeTruthy());
    expect(calls.find((c) => c.method === "POST")?.body).toEqual({ name: "Nights", handoff_weekday: 2, handoff_time: "09:00", anchor_date: "2030-01-09", member_ids: [2, 3] });
  });

  it("snaps the anchor to the chosen weekday", async () => {
    setup(<OnCall />, WRITE, routes());
    fireEvent.click(await screen.findByRole("button", { name: "New rotation" }));
    fireEvent.change(screen.getByLabelText("Anchor date"), { target: { value: "2030-01-07" } });
    fireEvent.change(screen.getByLabelText("Handoff weekday"), { target: { value: "4" } });
    expect(screen.getByLabelText("Anchor date")).toHaveValue("2030-01-11");
  });

  it("sends the new member order when editing", async () => {
    const calls = setup(<OnCall />, WRITE, routes({ "PATCH /api/oncall/rotations/4": () => json(ROTATION) }));
    fireEvent.click(await screen.findByRole("button", { name: "Edit Weekly" }));
    fireEvent.click(screen.getByRole("button", { name: "Move Alex Admin up" }));
    fireEvent.click(screen.getByRole("button", { name: "Save rotation" }));
    await waitFor(() => expect(calls.find((c) => c.method === "PATCH" && c.path === "/api/oncall/rotations/4")).toBeTruthy());
    expect(calls.find((c) => c.method === "PATCH")?.body).toMatchObject({ member_ids: [3, 2], active: true, handoff_weekday: 0 });
  });

  it("lists overrides and the next 4 weeks, and deletes an override", async () => {
    const calls = setup(<OnCall />, WRITE, routes({ "DELETE /api/oncall/overrides/9": () => json({}) }));
    expect(await screen.findByText("Holiday", { exact: false })).toBeInTheDocument();
    const table = await screen.findByRole("table");
    expect(within(table).getByText("Sam Tech")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Delete override for Alex Admin" }));
    await waitFor(() => expect(calls.some((c) => c.method === "DELETE" && c.path === "/api/oncall/overrides/9")).toBe(true));
  });

  it("hides every write control without schedule:write", async () => {
    setup(<OnCall />, READ, routes());
    expect(await screen.findByText("Weekly")).toBeInTheDocument();
    expect(await screen.findByText("View only")).toBeInTheDocument();
    for (const name of ["New rotation", "Edit Weekly", "Add override"]) expect(screen.queryByRole("button", { name })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Delete override/ })).not.toBeInTheDocument();
  });

  it("explains an empty list", async () => {
    setup(<OnCall />, READ, routes({ "GET /api/oncall/rotations": () => json([]) }));
    expect(await screen.findByText(/No rotations yet/)).toBeInTheDocument();
  });
});

describe("on-call widget", () => {
  const now = (over = {}) => ({ rotation_id: 4, rotation_name: "Weekly", user_id: 2, user_name: "Sam Tech", until: "2030-01-14T15:00:00Z", source: "rotation", ...over });

  it("shows the current person and the until time", async () => {
    setup(<OnCallWidget />, READ, { "GET /api/oncall/now": () => json([now()]) });
    expect(await screen.findByText("Sam Tech")).toBeInTheDocument();
    expect(await screen.findByText(/until Mon 14 Jan 09:00/)).toBeInTheDocument();
  });

  it("says when no one is on, and hides with no rotations or without schedule:read", async () => {
    setup(<OnCallWidget />, READ, { "GET /api/oncall/now": () => json([now({ user_id: null, user_name: null, until: null, source: null })]) });
    expect(await screen.findByText("No one on now")).toBeInTheDocument();
    cleanup();
    const calls = setup(<OnCallWidget />, READ, { "GET /api/oncall/now": () => json([]) });
    await waitFor(() => expect(calls.some((c) => c.path === "/api/oncall/now")).toBe(true));
    expect(screen.queryByLabelText("On call now")).not.toBeInTheDocument();
    cleanup();
    const none = setup(<OnCallWidget />, [], { "GET /api/oncall/now": () => json([now()]) });
    await waitFor(() => expect(none.some((c) => c.path === "/api/auth/me")).toBe(true));
    expect(none.some((c) => c.path === "/api/oncall/now")).toBe(false);
  });
});
