import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";

const json = (body: unknown, status = 200) => () => new Response(JSON.stringify(body), { status });
const ADMIN = ["org:read", "ticket:read", "ticket:write", "user:manage", "apikey:manage", "automation:manage"];
const me = (role: string, permissions: string[]) => ({ id: 1, email: "u@example.com", display_name: "Una", role, permissions });
const hook = (over = {}) => ({
  id: 3, name: "Ops channel", kind: "teams", url_host: "hooks.example.com", url_preview: "https://hooks.example.com/workflows/…",
  events: ["ticket.created", "ticket.sla_breached"], enabled: true, consecutive_failures: 0, last_success_at: null,
  last_failure_at: null, created_at: "2026-10-01T00:00:00Z", ...over,
});
const delivery = (over = {}) => ({
  id: 9, endpoint_id: 3, event_id: "e1", event_type: "ticket.created", status: "failed", attempts: 6, next_attempt_at: "2026-10-01T00:00:00Z",
  last_status_code: 500, last_error: "HTTP 500", delivered_at: null, created_at: "2026-10-01T00:00:00Z", ...over,
});

let calls: string[] = [];
function go(path: string, role: string, perms: string[], h: Record<string, () => Response>) {
  const handlers: Record<string, () => Response> = { "/api/auth/me": json(me(role, perms)), ...h };
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

describe("webhooks page", () => {
  it("lists endpoints with host preview, events and a failures badge", async () => {
    go("/webhooks", "admin", ADMIN, { "/api/webhooks": json([hook({ consecutive_failures: 2 })]) });
    expect(await screen.findByText("Ops channel")).toBeInTheDocument();
    expect(screen.getByText("https://hooks.example.com/workflows/…")).toBeInTheDocument();
    expect(screen.getAllByText("Microsoft Teams").length).toBeGreaterThan(1); // row label and the type option
    expect(screen.getByText("2 failed in a row")).toBeInTheDocument();
    expect(screen.getByText(/A ticket is created; A ticket breaches its SLA/)).toBeInTheDocument();
  });

  it("is hidden from people without automation:manage", async () => {
    go("/webhooks", "tech", ["ticket:read"], { "/api/webhooks": json([]) });
    await waitFor(() => expect(screen.queryByText("Webhooks")).toBeNull());
  });

  it("shows the signing secret once after create", async () => {
    go("/webhooks", "admin", ADMIN, {
      "/api/webhooks": json([]),
      "POST /api/webhooks": json({ endpoint: hook(), secret: "SIGNSECRETSIGNSECRETSIGNSECRET" }, 201),
    });
    fireEvent.change(await screen.findByLabelText("Name"), { target: { value: "Ops channel" } });
    fireEvent.change(screen.getByLabelText("Type"), { target: { value: "teams" } });
    fireEvent.change(screen.getByLabelText("URL"), { target: { value: "https://hooks.example.com/x" } });
    expect(screen.getByRole("button", { name: "Add webhook" })).toBeDisabled();
    fireEvent.click(screen.getByLabelText("A ticket is created"));
    fireEvent.click(screen.getByRole("button", { name: "Add webhook" }));
    expect(await screen.findByDisplayValue("SIGNSECRETSIGNSECRETSIGNSECRET")).toHaveAttribute("readonly");
    expect(screen.getByText("Store this secret now. It will not be shown again.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Copy" })).toBeInTheDocument();
    await waitFor(() => expect(calls.some((c) => c.startsWith("POST /api/webhooks ") && c.includes('"kind":"teams"') && c.includes('"ticket.created"'))).toBe(true));
    fireEvent.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(screen.queryByDisplayValue(/SIGNSECRET/)).toBeNull();
  });

  it("toggles enabled with a patch", async () => {
    go("/webhooks", "admin", ADMIN, {
      "/api/webhooks": json([hook()]),
      "PATCH /api/webhooks/3": json(hook({ enabled: false })),
    });
    fireEvent.click(await screen.findByLabelText("Enabled Ops channel"));
    await waitFor(() => expect(calls.some((c) => c.startsWith("PATCH /api/webhooks/3 ") && c.includes('"enabled":false'))).toBe(true));
  });

  it("the test button posts", async () => {
    go("/webhooks", "admin", ADMIN, {
      "/api/webhooks": json([hook()]),
      "POST /api/webhooks/3/test": json({ queued: 1 }, 202),
    });
    fireEvent.click(await screen.findByRole("button", { name: "Send test to Ops channel" }));
    await waitFor(() => expect(calls.some((c) => c.startsWith("POST /api/webhooks/3/test"))).toBe(true));
    expect(await screen.findByRole("status")).toHaveTextContent("Test sent");
  });

  it("shows the delivery log and retries a failed delivery", async () => {
    go("/webhooks", "admin", ADMIN, {
      "/api/webhooks": json([hook()]),
      "/api/webhooks/3/deliveries?limit=50": json([delivery(), delivery({ id: 10, status: "delivered", attempts: 1, last_error: null, last_status_code: 200 })]),
      "POST /api/webhooks/deliveries/9/retry": json(delivery({ status: "pending", attempts: 0 })),
    });
    fireEvent.click(await screen.findByRole("button", { name: "Deliveries for Ops channel" }));
    expect(await screen.findByText("HTTP 500")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /^Retry delivery/ }).length).toBe(1);
    fireEvent.click(screen.getByRole("button", { name: "Retry delivery 9" }));
    await waitFor(() => expect(calls.some((c) => c.startsWith("POST /api/webhooks/deliveries/9/retry"))).toBe(true));
  });
});
