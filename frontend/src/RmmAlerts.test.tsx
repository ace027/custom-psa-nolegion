import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";

const json = (body: unknown, status = 200) => () => new Response(JSON.stringify(body), { status });
const ADMIN = ["org:read", "org:write", "user:read", "ticket:read", "billing:read", "report:read", "integration:manage", "portal:manage"];
const me = { id: 1, email: "u@example.com", display_name: "Una", role: "admin", permissions: ADMIN };
const integ = (over = {}) => ({
  id: 1, kind: "ninjaone", name: "NinjaOne", base_url: "https://app.ninjarmm.com", config: {}, credentials_set: true,
  credentials_set_at: "2026-10-01T12:00:00Z", enabled: true, status: "ok", last_error: null, last_sync_at: "2026-10-02T12:00:00Z",
  sync_requested: false, alerts_polled_at: null, alerts_requested: false, alerts_last_error: null, ...over,
});
const alertRow = (over = {}) => ({
  id: 5, organization_id: 3, organization_name: "Acme", asset_id: 8, asset_name: "PC-1", ticket_id: 42, ticket_number: 107,
  severity: "MAJOR", message: "Disk almost full", state: "open", occurrences: 3, first_seen_at: "2026-10-02T12:00:00Z",
  last_seen_at: "2026-10-02T13:00:00Z", cleared_at: null, resolution: null, ...over,
});
const ticket = (over = {}) => ({
  id: 42, number: 107, organization_id: 3, organization_name: "Acme", contact_id: null, contact_name: null, site_id: null,
  queue_id: 1, queue_name: "Support", category_id: null, category_name: null, priority_id: 1, priority_name: "High", priority_rank: 1,
  status: "new", status_id: 1, assignee_id: null, assignee_name: null, subject: "Disk almost full", description: null,
  source: "rmm", asset_id: 8, asset_name: "PC-1", requester_email: null, needs_triage: false, sla_state: "none",
  sla_first_response_due: null, sla_resolution_due: null, first_responded_at: null,
  created_at: "2026-10-02T12:00:00Z", updated_at: "2026-10-02T12:00:00Z", ...over,
});

let calls: string[] = [];
function go(path: string, h: Record<string, () => Response>) {
  const handlers: Record<string, () => Response> = { "/api/auth/me": json(me), ...h };
  vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => {
    const key = init?.method && init.method !== "GET" ? `${init.method} ${url}` : url;
    calls.push(`${key} ${init?.body ?? ""}`);
    return Promise.resolve(handlers[key]?.() ?? new Response("{}", { status: 404 }));
  }));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><MemoryRouter initialEntries={[path]}><App /></MemoryRouter></QueryClientProvider>);
}
beforeEach(() => { calls = []; });
afterEach(() => vi.unstubAllGlobals());

const ALERTS_OPEN = "/api/integrations/1/alerts?state=open";

describe("RMM alerts card", () => {
  it("renders only for ninjaone, with defaults for an empty config", async () => {
    go("/integrations", {
      "/api/integrations": json([integ(), integ({ id: 2, kind: "hudu", name: "Hudu" })]),
      [ALERTS_OPEN]: json([]),
    });
    expect(await screen.findByText("Alerts to tickets")).toBeInTheDocument();
    expect(screen.getAllByText("Alerts to tickets")).toHaveLength(1);
    expect((screen.getByLabelText("Create tickets from alerts") as HTMLInputElement).checked).toBe(false);
    expect((screen.getByLabelText("Minimum severity") as HTMLSelectElement).value).toBe("MODERATE");
    expect((screen.getByLabelText("When an alert clears") as HTMLSelectElement).value).toBe("resolve_if_untouched");
    expect((screen.getByLabelText("Check every (minutes)") as HTMLInputElement).value).toBe("5");
    expect(screen.getByText("Not checked yet")).toBeInTheDocument();
    expect(await screen.findByText("No open alerts.")).toBeInTheDocument();
  });

  it("saves the merged config", async () => {
    go("/integrations", {
      "/api/integrations": json([integ({ config: { keep: "me" } })]),
      [ALERTS_OPEN]: json([]),
      "PATCH /api/integrations/1": json(integ()),
    });
    fireEvent.click(await screen.findByLabelText("Create tickets from alerts"));
    fireEvent.change(screen.getByLabelText("Minimum severity"), { target: { value: "CRITICAL" } });
    fireEvent.change(screen.getByLabelText("When an alert clears"), { target: { value: "note_only" } });
    fireEvent.change(screen.getByLabelText("Check every (minutes)"), { target: { value: "10" } });
    fireEvent.click(screen.getByRole("button", { name: "Save alert settings" }));
    await waitFor(() => expect(calls.some((c) => c.startsWith("PATCH /api/integrations/1 "))).toBe(true));
    const body = JSON.parse(calls.find((c) => c.startsWith("PATCH /api/integrations/1 "))!.split(" ").slice(2).join(" "));
    expect(body.config).toEqual({ keep: "me", alerts_enabled: true, alert_min_severity: "CRITICAL", alert_clear_rule: "note_only", alert_poll_minutes: 10 });
  });

  it("shows a server 409 inline", async () => {
    go("/integrations", {
      "/api/integrations": json([integ()]),
      [ALERTS_OPEN]: json([]),
      "PATCH /api/integrations/1": json({ detail: "alert_poll_minutes must be 1-60" }, 409),
    });
    fireEvent.click(await screen.findByRole("button", { name: "Save alert settings" }));
    expect(await screen.findByText("alert_poll_minutes must be 1-60")).toBeInTheDocument();
  });

  it("Check now is disabled while alerts are off and queues a poll when on", async () => {
    const { unmount } = go("/integrations", { "/api/integrations": json([integ()]), [ALERTS_OPEN]: json([]) });
    expect(await screen.findByRole("button", { name: "Check now" })).toBeDisabled();
    unmount();
    go("/integrations", {
      "/api/integrations": json([integ({ config: { alerts_enabled: true }, alerts_requested: true, alerts_last_error: "NinjaOne sign-in failed" })]),
      [ALERTS_OPEN]: json([]),
      "POST /api/integrations/1/alerts/poll": json(integ(), 202),
    });
    const btn = await screen.findByRole("button", { name: "Check now" });
    expect(btn).toBeEnabled();
    expect(screen.getByText("Check queued")).toBeInTheDocument();
    expect(screen.getByText("NinjaOne sign-in failed")).toBeInTheDocument();
    fireEvent.click(btn);
    await waitFor(() => expect(calls.some((c) => c.startsWith("POST /api/integrations/1/alerts/poll"))).toBe(true));
  });

  it("shows a deferred or suspicious warning from the last poll", async () => {
    const warning = "3 new alert(s) deferred to the next poll (limit 25 per poll)";
    go("/integrations", {
      "/api/integrations": json([integ({ config: { alerts_enabled: true }, alerts_last_error: warning })]),
      [ALERTS_OPEN]: json([]),
    });
    expect(await screen.findByText(warning)).toBeInTheDocument();
  });

  it("lists alerts with a ticket link and switches the filter", async () => {
    go("/integrations", {
      "/api/integrations": json([integ()]),
      [ALERTS_OPEN]: json([alertRow()]),
      "/api/integrations/1/alerts?state=cleared": json([alertRow({ id: 6, state: "cleared", cleared_at: "2026-10-03T12:00:00Z", resolution: "resolved", ticket_number: 108, ticket_id: 43 })]),
    });
    const link = await screen.findByRole("link", { name: "#107" });
    expect(link).toHaveAttribute("href", "/tickets/42");
    expect(screen.getByText("Disk almost full")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Alert filter"), { target: { value: "cleared" } });
    expect(await screen.findByRole("link", { name: "#108" })).toHaveAttribute("href", "/tickets/43");
    expect(calls.some((c) => c.startsWith("/api/integrations/1/alerts?state=cleared"))).toBe(true);
    expect(screen.getByText("Ticket resolved")).toBeInTheDocument();
  });
});

describe("ticket device chip", () => {
  it("shows the device link and RMM badge for an rmm ticket", async () => {
    go("/tickets/42", { "/api/tickets/42": json(ticket()) });
    expect(await screen.findByText("From RMM alert")).toBeInTheDocument();
    expect(screen.getByText(/Device:/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "PC-1" })).toHaveAttribute("href", "/organizations/3");
  });

  it("shows nothing for a ui ticket", async () => {
    go("/tickets/42", { "/api/tickets/42": json(ticket({ source: "ui", asset_id: null, asset_name: null })) });
    expect(await screen.findByText(/#107/)).toBeInTheDocument();
    expect(screen.queryByText("From RMM alert")).toBeNull();
    expect(screen.queryByText(/Device:/)).toBeNull();
  });
});
