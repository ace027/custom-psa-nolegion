import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import OrganizationDetail from "./pages/OrganizationDetail";

const json = (body: unknown, status = 200) => () => new Response(JSON.stringify(body), { status });
const me = (over = {}) => ({ contact_name: "Pat Payer", email: "pat@acme.com", organization_name: "Acme Corp", company_name: "Acme MSP", can_see_billing: false, can_see_all_tickets: false, can_see_devices: false, ...over });
const ticket = { id: 3, number: 10003, subject: "VPN slow", status: "open", created_at: "2026-09-30T12:00:00Z", updated_at: "2026-09-30T12:00:00Z", mine: true };
const detail = (over = {}) => ({ ...ticket, description: "It is slow", notes: [], ...over });
const file = (name: string, size: number) => {
  const f = new File(["x"], name, { type: "application/octet-stream" });
  Object.defineProperty(f, "size", { value: size });
  return f;
};

function mount(ui: React.ReactNode, path: string, handlers: Record<string, () => Response>, calls: string[] = []) {
  vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => {
    const key = init?.method && init.method !== "GET" ? `${init.method} ${url}` : url;
    calls.push(`${key} ${init?.body ?? ""}`);
    return Promise.resolve(handlers[key]?.() ?? new Response("{}", { status: 404 }));
  }));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><MemoryRouter initialEntries={[path]}>{ui}</MemoryRouter></QueryClientProvider>);
}
const portal = (path: string, h: Record<string, () => Response>, calls: string[] = []) => mount(<App />, path, h, calls);
const signedOut = { "/api/v1/portal/me": json({ detail: "no" }, 401) };

afterEach(() => { vi.unstubAllGlobals(); });

describe("portal Microsoft sign-in", () => {
  it("shows the button when login-options says sso, and navigates to the SSO start", async () => {
    const assign = vi.fn();
    vi.stubGlobal("location", { ...window.location, assign });
    portal("/portal", { ...signedOut, "/api/v1/portal/login-options": json({ sso: true }) });
    fireEvent.click(await screen.findByRole("button", { name: "Sign in with Microsoft" }));
    expect(assign).toHaveBeenCalledWith("/api/v1/portal/sso/login");
    expect(screen.getByLabelText("Email address")).toBeInTheDocument();
  });

  it("shows no button when sso is not configured", async () => {
    const calls: string[] = [];
    portal("/portal", { ...signedOut, "/api/v1/portal/login-options": json({ sso: false }) }, calls);
    await screen.findByLabelText("Email address");
    await waitFor(() => expect(calls.some((c) => c.startsWith("/api/v1/portal/login-options"))).toBe(true));
    expect(screen.queryByRole("button", { name: "Sign in with Microsoft" })).toBeNull();
  });

  it("shows the denied alert for ?sso=denied", async () => {
    portal("/portal?sso=denied", { ...signedOut, "/api/v1/portal/login-options": json({ sso: true }) });
    expect(await screen.findByRole("alert")).toHaveTextContent("We could not sign you in with Microsoft. Ask your IT contact to check your account, or use an email link.");
  });

  it("shows an info message, not an error, for ?sso=confirm", async () => {
    portal("/portal?sso=confirm", { ...signedOut, "/api/v1/portal/login-options": json({ sso: true }) });
    expect(await screen.findByRole("status")).toHaveTextContent("Check your email: we sent a link to confirm your Microsoft account. It works once.");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});

describe("My details", () => {
  const base = { "/api/v1/portal/me": json(me({ phone: "555-0100", title: "Owner" })), "/api/v1/portal/tickets": json([]) };
  it("shows email read-only and saves name, phone and title", async () => {
    const calls: string[] = [];
    portal("/portal/me", { ...base, "PATCH /api/v1/portal/me/contact": json(me({ contact_name: "Patricia Payer" })) }, calls);
    expect(await screen.findByText("Contact us to change your email")).toBeInTheDocument();
    expect(screen.getByLabelText("Email address")).toHaveAttribute("readonly");
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Patricia Payer" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Saved");
    const sent = calls.find((c) => c.startsWith("PATCH /api/v1/portal/me/contact"))!;
    expect(sent).toContain('"name":"Patricia Payer"');
    expect(sent).toContain('"phone":"555-0100"');
    expect(sent).not.toContain("email");
  });

  it("shows the API error inline", async () => {
    portal("/portal/me", { ...base, "PATCH /api/v1/portal/me/contact": json({ detail: "Name is too long" }, 422) });
    await screen.findByText("Contact us to change your email");
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText(/Name is too long/)).toBeInTheDocument();
    expect(screen.queryByText("Saved")).toBeNull();
  });
});

describe("portal attachments", () => {
  const atts = [{ id: 9, filename: "screenshot.png", size_bytes: 2048, created_at: "2026-09-30T12:00:00Z" }];
  const h = (status = "open", extra: Record<string, () => Response> = {}) => ({
    "/api/v1/portal/me": json(me()), "/api/v1/portal/tickets": json([ticket]),
    "/api/v1/portal/tickets/3": json(detail({ status })), "/api/v1/portal/tickets/3/attachments": json(atts), ...extra,
  });
  const input = () => document.querySelector('input[type="file"]') as HTMLInputElement;

  it("lists files as download buttons", async () => {
    portal("/portal/tickets/3", h());
    expect(await screen.findByRole("button", { name: "screenshot.png" })).toBeInTheDocument();
  });

  it("shows loading text before the list arrives", async () => {
    portal("/portal/tickets/3", h());
    expect(await screen.findByText("Loading files…")).toBeInTheDocument();
    await screen.findByRole("button", { name: "screenshot.png" });
    expect(screen.queryByText("Loading files…")).toBeNull();
  });

  it("rejects an oversized file and a wrong type without a request", async () => {
    const calls: string[] = [];
    portal("/portal/tickets/3", h("open"), calls);
    await screen.findByRole("button", { name: "screenshot.png" });
    fireEvent.change(input(), { target: { files: [file("big.pdf", 10 * 1024 * 1024 + 1)] } });
    expect(await screen.findByRole("alert")).toHaveTextContent("larger than 10 MB");
    fireEvent.change(input(), { target: { files: [file("run.exe", 10)] } });
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("not allowed"));
    expect(calls.some((c) => c.startsWith("POST"))).toBe(false);
  });

  it("uploads an allowed file as base64", async () => {
    const calls: string[] = [];
    portal("/portal/tickets/3", h("open", { "POST /api/v1/portal/tickets/3/attachments": json(atts[0], 201) }), calls);
    await screen.findByRole("button", { name: "screenshot.png" });
    fireEvent.change(input(), { target: { files: [new File(["hello"], "notes.txt", { type: "text/plain" })] } });
    await waitFor(() => expect(calls.some((c) => c.startsWith("POST /api/v1/portal/tickets/3/attachments"))).toBe(true));
    const sent = calls.find((c) => c.startsWith("POST"))!;
    expect(sent).toContain('"filename":"notes.txt"');
    expect(sent).toContain(`"content_base64":"${btoa("hello")}"`);
    expect(await screen.findByText("File attached.")).toBeInTheDocument();
  });

  it("shows the API error on a failed upload", async () => {
    portal("/portal/tickets/3", h("open", { "POST /api/v1/portal/tickets/3/attachments": json({ detail: "Too many uploads, try later" }, 429) }));
    await screen.findByRole("button", { name: "screenshot.png" });
    fireEvent.change(input(), { target: { files: [new File(["hello"], "notes.txt")] } });
    expect(await screen.findByText(/Too many uploads, try later/)).toBeInTheDocument();
  });

  it("has no upload input on a closed ticket", async () => {
    portal("/portal/tickets/3", h("closed"));
    await screen.findByRole("button", { name: "screenshot.png" });
    expect(input()).toBeNull();
  });
});

describe("portal CSV exports", () => {
  const assets = { total: 0, as_of: "2026-10-01", counts: { expired: 0, expiring_30: 0, expiring_60: 0, expiring_90: 0, in_warranty: 0, unknown: 0 }, devices: [] };
  const tickets = { "/api/v1/portal/me": json(me()), "/api/v1/portal/tickets": json([ticket]) };
  const csv = (headers: Record<string, string> = {}) => () => new Response("a,b", { status: 200, headers });

  it("offers tickets export; invoices only for billing contacts", async () => {
    portal("/portal/tickets", tickets);
    expect(await screen.findByRole("button", { name: /export tickets/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /export invoices/i })).toBeNull();
  });

  it("offers the invoices and devices exports", async () => {
    portal("/portal/invoices", { "/api/v1/portal/me": json(me({ can_see_billing: true })), "/api/v1/portal/invoices": json([]) });
    expect(await screen.findByRole("button", { name: /export invoices/i })).toBeInTheDocument();
    portal("/portal/devices", { "/api/v1/portal/me": json(me({ can_see_devices: true })), "/api/v1/portal/assets": json(assets) });
    expect(await screen.findByRole("button", { name: /export devices/i })).toBeInTheDocument();
  });

  it("shows an alert and saves nothing when the export returns 401", async () => {
    const create = vi.fn(() => "blob:x");
    vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: create, revokeObjectURL: vi.fn() }));
    portal("/portal/tickets", { ...tickets, "/api/v1/portal/export/tickets.csv": json({ detail: "Not signed in" }, 401) });
    fireEvent.click(await screen.findByRole("button", { name: /export tickets/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent("session may have expired");
    expect(screen.getByRole("alert")).toHaveTextContent("Not signed in");
    expect(create).not.toHaveBeenCalled();
  });

  it("downloads and shows the truncation note", async () => {
    const create = vi.fn(() => "blob:x");
    const revoke = vi.fn();
    vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: create, revokeObjectURL: revoke }));
    portal("/portal/tickets", { ...tickets, "/api/v1/portal/export/tickets.csv": csv({ "X-Export-Truncated": "true" }) });
    fireEvent.click(await screen.findByRole("button", { name: /export tickets/i }));
    expect(await screen.findByRole("status")).toHaveTextContent("Only the first 10,000 rows were exported.");
    expect(create).toHaveBeenCalledOnce();
    expect(revoke).toHaveBeenCalledWith("blob:x");
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

describe("staff SSO fields", () => {
  const org = { id: 12, uuid: "u", rmm_client_id: null, name: "Acme", status: "active", billing_address: null, notes: null, assets_published: false, entra_tenant_id: null, archived_at: null };
  const contact = (over = {}) => ({ id: 1, uuid: "c", organization_id: 12, site_id: null, name: "Pat", email: "pat@acme.com", phone: null, title: null, is_primary: false, is_billing_contact: false, portal_access: true, portal_org_tickets: false, portal_assets: false, entra_linked: true, archived_at: null, ...over });
  const staff = (contacts: unknown[], calls: string[], perms = ["org:write", "org:read", "portal:manage"]) => mount(
    <Routes><Route path="/organizations/:id" element={<OrganizationDetail />} /></Routes>,
    "/organizations/12",
    {
      "/api/v1/auth/me": json({ id: 1, email: "a@x.com", display_name: "A", role: "admin", permissions: perms, notify_assigned: true, notify_sla: true, notify_reply: true }),
      "/api/v1/organizations/12": json(org),
      "/api/v1/organizations/12/sites?include_archived=true": json([]),
      "/api/v1/organizations/12/contacts?include_archived=true": json(contacts),
      "PATCH /api/v1/organizations/12": json(org),
      "PATCH /api/v1/contacts/1": json(contact({ entra_linked: false })),
    },
    calls,
  );

  it("saves the tenant id", async () => {
    const calls: string[] = [];
    staff([], calls);
    const field = await screen.findByLabelText("Client Entra tenant ID");
    expect(screen.getByText(/enables portal Microsoft sign-in/)).toBeInTheDocument();
    fireEvent.change(field, { target: { value: "11111111-2222-3333-4444-555555555555" } });
    fireEvent.click(screen.getAllByRole("button", { name: "Save" })[0]);
    await waitFor(() => expect(calls.some((c) => c.startsWith("PATCH /api/v1/organizations/12") && c.includes('"entra_tenant_id":"11111111-2222-3333-4444-555555555555"'))).toBe(true));
  });

  it("shows the tenant id read-only without portal:manage and does not send it", async () => {
    const calls: string[] = [];
    staff([], calls, ["org:write", "org:read"]);
    const field = await screen.findByLabelText("Client Entra tenant ID");
    expect(field).toBeDisabled();
    fireEvent.click(screen.getAllByRole("button", { name: "Save" })[0]);
    await waitFor(() => expect(calls.some((c) => c.startsWith("PATCH /api/v1/organizations/12"))).toBe(true));
    expect(calls.some((c) => c.includes("entra_tenant_id"))).toBe(false);
  });

  it("shows the Microsoft linked badge and unlinks", async () => {
    const calls: string[] = [];
    staff([contact()], calls);
    expect(await screen.findByText("Microsoft linked")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Unlink Microsoft" }));
    await waitFor(() => expect(calls.some((c) => c.startsWith("PATCH /api/v1/contacts/1") && c.includes('"unlink_entra":true'))).toBe(true));
  });

  it("shows no badge for an unlinked contact", async () => {
    staff([contact({ entra_linked: false })], []);
    await screen.findByText(/Pat/);
    expect(screen.queryByText("Microsoft linked")).toBeNull();
  });
});
