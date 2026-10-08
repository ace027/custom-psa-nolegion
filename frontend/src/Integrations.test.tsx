import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";

const json = (body: unknown, status = 200) => () => new Response(JSON.stringify(body), { status });
const ADMIN = ["org:read", "org:write", "user:read", "ticket:read", "billing:read", "report:read", "integration:manage", "portal:manage"];
const TECH = ["org:read", "org:write", "user:read", "ticket:read", "billing:read"];
const me = (role: string, permissions: string[]) => ({ id: 1, email: "u@example.com", display_name: "Una", role, permissions });
const integ = (over = {}) => ({
  id: 1, kind: "ninjaone", name: "NinjaOne", base_url: "https://app.ninjarmm.com", config: {}, credentials_set: true,
  credentials_set_at: "2026-10-01T12:00:00Z", enabled: true, status: "ok", last_error: null, last_sync_at: "2026-10-02T12:00:00Z", sync_requested: false, ...over,
});
const asset = (over = {}) => ({
  id: 1, organization_id: 3, organization_name: "Acme", kind: "computer", name: "PC-1", manufacturer: "Dell", model: "Latitude", serial: "SN1",
  warranty_start: null, warranty_end: "2025-01-01", warranty_status: "expired", warranty_overridden: false, conflict: false, retired_at: null, ...over,
});

let calls: string[] = [];
function go(path: string, role: string, perms: string[], h: Record<string, () => Response>) {
  const handlers: Record<string, () => Response> = { "/api/auth/me": json(me(role, perms)), ...h };
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

describe("integrations", () => {
  it("shows status and never any credential, and tests the connection", async () => {
    go("/integrations", "admin", ADMIN, {
      "/api/integrations": json([integ({ status: "error", last_error: "NinjaOne sign-in failed (HTTP 401)" })]),
      "POST /api/integrations/1/test": json({ ok: false, error: "NinjaOne sign-in failed (HTTP 401)" }),
    });
    expect(await screen.findByText("NinjaOne (NinjaOne)")).toBeInTheDocument();
    expect(screen.getAllByText(/HTTP 401/)[0]).toBeInTheDocument();
    expect(screen.getByText(/set /)).toBeInTheDocument();
    expect(screen.queryByDisplayValue(/secret/i)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Test connection" }));
    expect(await screen.findByText(/Connection failed/)).toBeInTheDocument();
  });

  it("credential fields are password inputs and are sent only when connecting", async () => {
    go("/integrations", "admin", ADMIN, { "/api/integrations": json([]), "POST /api/integrations": json(integ(), 201) });
    await screen.findByText("Connect a vendor");
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Ninja" } });
    const secret = screen.getByLabelText("Client secret") as HTMLInputElement;
    expect(secret.type).toBe("password");
    fireEvent.change(screen.getByLabelText("Client ID"), { target: { value: "cid" } });
    fireEvent.change(secret, { target: { value: "shh" } });
    fireEvent.click(screen.getByRole("button", { name: "Connect" }));
    await waitFor(() => expect(calls.some((c) => c.startsWith("POST /api/integrations ") && c.includes('"client_secret":"shh"'))).toBe(true));
  });

  it("lists vendor clients that still need mapping and maps one", async () => {
    go("/integrations", "admin", ADMIN, {
      "/api/integrations": json([integ()]),
      "/api/integrations/1/clients": json([{ id: 9, external_id: "7", external_name: "Acme", organization_id: null, ignored: false, needs_mapping: true, suggested_organization_id: 3 }]),
      "/api/integrations/1/runs": json([]),
      "/api/organizations": json([{ id: 3, name: "Acme Corp", status: "active" }]),
      "PUT /api/integrations/1/clients/9": json({}),
    });
    fireEvent.click(await screen.findByRole("button", { name: "Clients and history" }));
    expect(await screen.findByText("1 to map")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Use suggested match" }));
    await waitFor(() => expect(calls.some((c) => c.startsWith("PUT /api/integrations/1/clients/9") && c.includes('"organization_id":3'))).toBe(true));
  });

  it("techs do not get the integrations page", async () => {
    go("/integrations", "tech", TECH, { "/api/tickets": json([]) });
    await waitFor(() => expect(screen.queryByText("Connect a vendor")).toBeNull());
    expect(screen.queryByRole("link", { name: "Integrations" })).toBeNull();
  });
});

describe("warranty", () => {
  it("lists devices with a status badge and a CSV link that carries the filters", async () => {
    go("/warranty", "admin", ADMIN, {
      "/api/organizations?limit=200": json({ items: [{ id: 3, name: "Acme", status: "active" }], total: 1 }),
      "/api/reports/warranty": json({ as_of: "2026-10-08", total: 1, counts: { expired: 1, expiring_30: 0, expiring_60: 0, expiring_90: 0, in_warranty: 0, unknown: 0 }, rows: [asset()] }),
      "/api/reports/warranty?within_days=30": json({ as_of: "2026-10-08", total: 0, counts: {}, rows: [] }),
    });
    const row = (await screen.findByText("PC-1")).closest("tr")!;
    expect(await screen.findByRole("option", { name: "Acme" })).toBeInTheDocument(); // client filter is populated
    expect(within(row).getByText("Expired")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Download CSV" })).toHaveAttribute("href", "/api/reports/warranty.csv");
    fireEvent.change(screen.getByLabelText("Expiring within"), { target: { value: "30" } });
    await waitFor(() => expect(screen.getByRole("link", { name: "Download CSV" })).toHaveAttribute("href", "/api/reports/warranty.csv?within_days=30"));
  });

  it("an org page lets a tech correct a date with a reason", async () => {
    go("/organizations/3", "tech", TECH, {
      "/api/organizations/3": json({ id: 3, name: "Acme", status: "active", billing_address: null, notes: null, assets_published: false, archived_at: null }),
      "/api/organizations/3/sites?include_archived=true": json([]),
      "/api/organizations/3/contacts?include_archived=true": json([]),
      "/api/organizations/3/assets?include_retired=false": json([asset({ conflict: true })]),
      "PUT /api/assets/1/overrides/warranty_end": json({}),
    });
    expect(await screen.findByText("sources disagree")).toBeInTheDocument();
    expect(screen.queryByText(/Publish to portal/)).toBeNull(); // admin-only
    fireEvent.click(screen.getByRole("button", { name: "Correct date" }));
    fireEvent.change(screen.getByLabelText("Warranty ends"), { target: { value: "2028-01-01" } });
    fireEvent.change(screen.getByLabelText("Reason"), { target: { value: "Renewed, invoice 12" } });
    fireEvent.click(within(screen.getByText(/Correct the warranty end date/).closest("form")!).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(calls.some((c) => c.startsWith("PUT /api/assets/1/overrides/warranty_end") && c.includes("Renewed, invoice 12"))).toBe(true));
  });
});

describe("portal devices", () => {
  const pme = (over = {}) => ({ contact_name: "Pat", email: "pat@acme.com", organization_name: "Acme", company_name: "MSP", can_see_billing: false, can_see_all_tickets: false, can_see_devices: true, ...over });
  it("shows the Devices tab only when the contact may see it, without serials", async () => {
    go("/portal/devices", "x", [], {
      "/api/portal/me": json(pme()),
      "/api/portal/assets": json({ as_of: "2026-10-08", total: 2, counts: { expired: 1, expiring_30: 1, expiring_60: 0, expiring_90: 0, in_warranty: 0, unknown: 0 }, devices: [
        { name: "PC-1", kind: "computer", manufacturer: "Dell", model: "Latitude", warranty_end: "2025-01-01", warranty_status: "expired" },
        { name: "PC-2", kind: "computer", manufacturer: null, model: null, warranty_end: "2026-10-20", warranty_status: "expiring_30" },
      ] }),
    });
    expect(await screen.findByText(/2 device\(s\) as of 2026-10-08/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Devices" })).toBeInTheDocument();
    expect(screen.queryByText("SN1")).toBeNull();
  });

  it("hides the tab otherwise", async () => {
    go("/portal/tickets", "x", [], { "/api/portal/me": json(pme({ can_see_devices: false })), "/api/portal/tickets": json([]) });
    await screen.findByText(/Pat · Acme/);
    expect(screen.queryByRole("link", { name: "Devices" })).toBeNull();
  });
});
