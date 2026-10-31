import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";

const json = (body: unknown, status = 200) => () => new Response(JSON.stringify(body), { status });
const ADMIN = ["org:read", "ticket:read", "ticket:write", "user:manage", "apikey:manage", "automation:manage"];
const me = (role: string, permissions: string[]) => ({ id: 1, email: "u@example.com", display_name: "Una", role, permissions });
const rule = (over = {}) => ({
  id: 4, name: "Route security", enabled: true, trigger: "ticket.created",
  conditions: [{ field: "queue_id", op: "eq", value: 2 }], actions: [{ type: "assign", user_id: 7 }],
  position: 0, disabled_reason: null, fire_count: 3, last_fired_at: "2026-10-01T00:00:00Z", archived_at: null,
  created_at: "2026-10-01T00:00:00Z", updated_at: "2026-10-01T00:00:00Z", ...over,
});
const LOOKUPS = {
  "/api/v1/queues": json([{ id: 1, name: "Support", archived_at: null, is_default: true }, { id: 2, name: "Security", archived_at: null, is_default: false }]),
  "/api/v1/priorities": json([{ id: 1, name: "Urgent", rank: 1, archived_at: null }, { id: 2, name: "Normal", rank: 3, archived_at: null }]),
  "/api/v1/users": json([{ id: 7, display_name: "Terry Tech", role: "tech", is_active: true }]),
  "/api/v1/categories": json([]),
  "/api/v1/ticket-types": json([]),
  "/api/v1/webhooks": json([]),
  "/api/v1/organizations": json([]),
};

let calls: string[] = [];
function go(path: string, role: string, perms: string[], h: Record<string, () => Response>) {
  const handlers: Record<string, () => Response> = { "/api/v1/auth/me": json(me(role, perms)), ...LOOKUPS, ...h };
  vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => {
    const k = init?.method && init.method !== "GET" ? `${init.method} ${url}` : url;
    calls.push(`${k} ${init?.body ?? ""}`);
    return Promise.resolve(handlers[k]?.() ?? new Response("{}", { status: 404 }));
  }));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><MemoryRouter initialEntries={[path]}><App /></MemoryRouter></QueryClientProvider>);
}
beforeEach(() => { calls = []; });
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

describe("automation page", () => {
  it("lists rules with trigger, fired count and a disabled warning", async () => {
    go("/automation", "admin", ADMIN, {
      "/api/v1/automation/rules": json([rule(), rule({ id: 5, name: "Noisy", enabled: false, disabled_reason: "Fired more than 200 times in an hour" })]),
    });
    expect(await screen.findByText("Route security")).toBeInTheDocument();
    expect(screen.getAllByText("A ticket is created").length).toBeGreaterThan(1);
    expect(screen.getAllByText("Fired 3 times").length).toBe(2);
    expect(screen.getByText("Switched off: Fired more than 200 times in an hour")).toBeInTheDocument();
  });

  it("is hidden from people without automation:manage", async () => {
    go("/automation", "tech", ["ticket:read"], { "/api/v1/automation/rules": json([]) });
    await waitFor(() => expect(screen.queryByText("Automation")).toBeNull());
  });

  it("builds a rule and saves the right JSON", async () => {
    go("/automation", "admin", ADMIN, {
      "/api/v1/automation/rules": json([]),
      "POST /api/v1/automation/rules": json(rule(), 201),
    });
    fireEvent.change(await screen.findByLabelText("Name"), { target: { value: "Route security" } });
    expect(screen.getByRole("button", { name: "Save rule" })).toBeDisabled(); // no action yet
    fireEvent.click(screen.getByRole("button", { name: "Add condition" }));
    fireEvent.change(screen.getByLabelText("Condition field 1"), { target: { value: "queue_id" } });
    await screen.findByRole("option", { name: "Security" });
    fireEvent.change(screen.getByLabelText("Condition value 1"), { target: { value: "2" } });
    fireEvent.click(screen.getByRole("button", { name: "Add action" }));
    fireEvent.change(screen.getByLabelText("Action type 1"), { target: { value: "assign" } });
    expect(screen.getByRole("button", { name: "Save rule" })).toBeDisabled(); // person not chosen
    await screen.findByRole("option", { name: "Terry Tech" });
    fireEvent.change(screen.getByLabelText("Action person 1"), { target: { value: "7" } });
    fireEvent.click(screen.getByRole("button", { name: "Save rule" }));
    await waitFor(() => expect(calls.some((c) => c.startsWith("POST /api/v1/automation/rules "))).toBe(true));
    const body = JSON.parse(calls.find((c) => c.startsWith("POST /api/v1/automation/rules "))!.replace("POST /api/v1/automation/rules ", ""));
    expect(body).toEqual({
      name: "Route security", trigger: "ticket.created", enabled: true, position: 0,
      conditions: [{ field: "queue_id", op: "eq", value: 2 }],
      actions: [{ type: "assign", user_id: 7 }],
    });
  });

  it("limits operators per field and hides alert severity on ticket triggers", async () => {
    go("/automation", "admin", ADMIN, { "/api/v1/automation/rules": json([]) });
    fireEvent.click(await screen.findByRole("button", { name: "Add condition" }));
    expect(within(screen.getByLabelText("Condition field 1")).queryByText("Alert severity")).toBeNull();
    expect(within(screen.getByLabelText("Condition operator 1")).queryByText("contains")).toBeNull();
    fireEvent.change(screen.getByLabelText("Condition field 1"), { target: { value: "subject" } });
    expect(within(screen.getByLabelText("Condition operator 1")).getByText("contains")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("When"), { target: { value: "rmm_alert.opened" } });
    expect(within(screen.getByLabelText("Condition field 1")).getByText("Alert severity")).toBeInTheDocument();
  });

  it("toggles enabled with a patch", async () => {
    go("/automation", "admin", ADMIN, {
      "/api/v1/automation/rules": json([rule()]),
      "PATCH /api/v1/automation/rules/4": json(rule({ enabled: false })),
    });
    fireEvent.click(await screen.findByLabelText("Enabled Route security"));
    await waitFor(() => expect(calls.some((c) => c.startsWith("PATCH /api/v1/automation/rules/4 ") && c.includes('"enabled":false'))).toBe(true));
  });

  it("tests against a ticket and renders matched rows and would-run actions", async () => {
    go("/automation", "admin", ADMIN, {
      "/api/v1/automation/rules": json([rule()]),
      "POST /api/v1/automation/rules/test": json({
        matched: false, trigger: "ticket.created",
        conditions: [{ field: "queue_id", op: "eq", value: 2, actual: 1, matched: false }],
        actions: [],
      }),
    });
    fireEvent.click(await screen.findByRole("button", { name: "Edit Route security" }));
    fireEvent.change(screen.getByLabelText("Test against ticket #"), { target: { value: "55" } });
    await screen.findByRole("option", { name: "Terry Tech" });
    fireEvent.click(screen.getByRole("button", { name: "Test rule" }));
    expect(await screen.findByText("This rule would not run on that ticket.")).toBeInTheDocument();
    expect(screen.getByText(/Did not match/)).toBeInTheDocument();
    expect(screen.getByText(/ticket has 1/)).toBeInTheDocument();
    const sent = JSON.parse(calls.find((c) => c.startsWith("POST /api/v1/automation/rules/test "))!.replace("POST /api/v1/automation/rules/test ", ""));
    expect(sent.ticket_id).toBe(55);
    expect(sent.rule.conditions).toEqual([{ field: "queue_id", op: "eq", value: 2 }]);
  });

  it("shows would-run actions when the rule matches", async () => {
    go("/automation", "admin", ADMIN, {
      "/api/v1/automation/rules": json([rule()]),
      "POST /api/v1/automation/rules/test": json({
        matched: true, trigger: "ticket.created",
        conditions: [{ field: "queue_id", op: "eq", value: 2, actual: 2, matched: true }],
        actions: [{ type: "assign", params: { user_id: 7 }, status: "would_run", detail: "Assign to Terry Tech" }],
      }),
    });
    fireEvent.click(await screen.findByRole("button", { name: "Edit Route security" }));
    fireEvent.change(screen.getByLabelText("Test against ticket #"), { target: { value: "55" } });
    fireEvent.click(screen.getByRole("button", { name: "Test rule" }));
    expect(await screen.findByText("This rule would run on that ticket.")).toBeInTheDocument();
    expect(screen.getByText("Assign to Terry Tech")).toBeInTheDocument();
  });

  it("shows run history", async () => {
    go("/automation", "admin", ADMIN, {
      "/api/v1/automation/rules": json([rule()]),
      "/api/v1/automation/rules/4/runs?limit=50": json([{
        id: 1, rule_id: 4, event_id: "e1", event_type: "ticket.created", ticket_id: 12, matched: true, created_at: "2026-10-01T00:00:00Z",
        trace: { conditions: [], actions: [{ type: "assign", params: {}, status: "done", detail: "Assigned to Terry Tech" }] },
      }]),
    });
    fireEvent.click(await screen.findByRole("button", { name: "History for Route security" }));
    expect(await screen.findByText("assign: done (Assigned to Terry Tech)")).toBeInTheDocument();
  });

  it("archives only after confirming", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    go("/automation", "admin", ADMIN, {
      "/api/v1/automation/rules": json([rule()]),
      "POST /api/v1/automation/rules/4/archive": json(rule({ archived_at: "2026-10-02T00:00:00Z", enabled: false })),
    });
    fireEvent.click(await screen.findByRole("button", { name: "Edit Route security" }));
    fireEvent.click(screen.getByRole("button", { name: "Archive rule" }));
    expect(confirm).toHaveBeenCalled();
    await waitFor(() => expect(calls.some((c) => c.startsWith("POST /api/v1/automation/rules/4/archive"))).toBe(true));
  });
});
