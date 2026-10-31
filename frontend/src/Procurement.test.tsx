import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";

const json = (body: unknown, status = 200) => () => new Response(JSON.stringify(body), { status });
const WRITE = ["procurement:read", "procurement:write"];
const READ = ["procurement:read"];
const me = (role: string, permissions: string[]) => ({ id: 1, email: "u@example.com", display_name: "Una", role, permissions });
const TS = "2026-10-01T12:00:00Z";

const line = (over = {}) => ({
  id: 11, purchase_order_id: 7, position: 1, product_id: null, description: "Laptop", quantity: 2, unit_cost_cents: 12345,
  received_quantity: 0, serialised: true, billable: true, taxable: true, markup_bp: 1500, ...over,
});
const po = (over = {}) => ({
  id: 7, number: "PO-0007", vendor_id: 1, vendor_name: "Acme Supply", organization_id: null, status: "ordered", ordered_on: "2026-10-01",
  expected_on: null, vendor_reference: null, notes: null, created_by: 1, created_at: TS, updated_at: TS, lines: [line()], ...over,
});
const item = (over = {}) => ({
  id: 21, purchase_order_line_id: 11, product_id: null, description: "Laptop", serial_number: "SN-1", quantity: 1, unit_cost_cents: 12345,
  status: "in_stock", organization_id: null, organization_name: null, asset_id: null, delivered_on: null, markup_bp: null,
  product_charge_id: null, received_on: "2026-10-02", notes: null, created_at: TS, updated_at: TS, ...over,
});
const delivered = (over = {}) => item({ status: "delivered", organization_id: 3, organization_name: "Acme", delivered_on: "2026-10-03", markup_bp: 1500, product_charge_id: 5, ...over });

let calls: string[] = [];
function go(path: string, role: string, perms: string[], h: Record<string, () => Response>) {
  const handlers: Record<string, () => Response> = { "/api/v1/auth/me": json(me(role, perms)), ...h };
  vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => {
    const key = init?.method && init.method !== "GET" ? `${init.method} ${url}` : url;
    calls.push(`${key} ${init?.body ?? ""}`);
    return Promise.resolve(handlers[key]?.() ?? new Response("{}", { status: 404 }));
  }));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><MemoryRouter initialEntries={[path]}><App /></MemoryRouter></QueryClientProvider>);
}
const called = (prefix: string, part = "") => calls.some((c) => c.startsWith(prefix) && c.includes(part));
beforeEach(() => { calls = []; });
afterEach(() => vi.unstubAllGlobals());

describe("receive dialog", () => {
  const page = (extra: Record<string, () => Response> = {}) => ({ "/api/v1/procurement/purchase-orders/7": json(po()), ...extra });

  it("renders one serial input per unit and posts the serials", async () => {
    go("/procurement/purchase-orders/7", "admin", WRITE, page({ "POST /api/v1/procurement/purchase-orders/7/receive": json([item(), item({ id: 22 })], 201) }));
    fireEvent.click(await screen.findByRole("button", { name: "Receive Laptop" }));
    expect(await screen.findByLabelText("Serial number 1")).toBeInTheDocument();
    expect(screen.getByLabelText("Serial number 2")).toBeInTheDocument();
    expect(screen.queryByLabelText("Serial number 3")).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Serial number 1"), { target: { value: "SN-1" } });
    fireEvent.click(screen.getByRole("button", { name: "Receive stock" }));
    expect(await screen.findByText(/Enter 2 serial numbers/)).toBeInTheDocument();
    expect(called("POST")).toBe(false);
    fireEvent.change(screen.getByLabelText("Serial number 2"), { target: { value: "SN-2" } });
    fireEvent.click(screen.getByRole("button", { name: "Receive stock" }));
    await waitFor(() => expect(called("POST /api/v1/procurement/purchase-orders/7/receive", '"serials":["SN-1","SN-2"]')).toBe(true));
    expect(called("POST /api/v1/procurement/purchase-orders/7/receive", '"line_id":11')).toBe(true);
  });

  it("shows a duplicate serial error from the server inline", async () => {
    go("/procurement/purchase-orders/7", "admin", WRITE, page({ "POST /api/v1/procurement/purchase-orders/7/receive": json({ detail: "Serial number SN-1 is already in inventory" }, 409) }));
    fireEvent.click(await screen.findByRole("button", { name: "Receive Laptop" }));
    fireEvent.change(await screen.findByLabelText("Serial number 1"), { target: { value: "SN-1" } });
    fireEvent.change(screen.getByLabelText("Serial number 2"), { target: { value: "SN-2" } });
    fireEvent.click(screen.getByRole("button", { name: "Receive stock" }));
    expect(await screen.findByText("Serial number SN-1 is already in inventory")).toBeInTheDocument();
  });
});

describe("new purchase order", () => {
  it("sends a markup of 15 percent as 1500 basis points", async () => {
    go("/procurement", "admin", WRITE, {
      "/api/v1/procurement/purchase-orders": json([]),
      "/api/v1/procurement/vendors": json([{ id: 1, name: "Acme Supply", account_number: null, email: null, phone: null, website: null, notes: null, archived_at: null, created_at: TS, updated_at: TS }]),
      "/api/v1/organizations": json([]),
      "POST /api/v1/procurement/purchase-orders": json(po({ id: 8, status: "draft", number: null }), 201),
      "/api/v1/procurement/purchase-orders/8": json(po({ id: 8, status: "draft", number: null })),
    });
    expect(await screen.findByText("No purchase orders yet.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "New purchase order" }));
    await screen.findByRole("option", { name: "Acme Supply" });
    fireEvent.change(screen.getByLabelText("Vendor"), { target: { value: "1" } });
    fireEvent.change(screen.getByLabelText("Line 1 description"), { target: { value: "Switch" } });
    fireEvent.change(screen.getByLabelText("Line 1 unit cost ($)"), { target: { value: "123.45" } });
    fireEvent.change(screen.getByLabelText("Line 1 markup (%)"), { target: { value: "15" } });
    fireEvent.click(screen.getByRole("button", { name: "Create purchase order" }));
    await waitFor(() => expect(called("POST /api/v1/procurement/purchase-orders", '"markup_bp":1500')).toBe(true));
    expect(called("POST /api/v1/procurement/purchase-orders", '"unit_cost_cents":12345')).toBe(true);
  });
});

describe("read-only user", () => {
  it("hides write actions on the order page", async () => {
    go("/procurement/purchase-orders/7", "read_only", READ, { "/api/v1/procurement/purchase-orders/7": json(po({ status: "draft" })) });
    expect(await screen.findByText("Laptop")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Order" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Receive/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Cancel/ })).not.toBeInTheDocument();
  });

  it("hides deliver, consume and undo on the inventory page", async () => {
    go("/procurement/inventory", "read_only", READ, {
      "/api/v1/procurement/inventory": json([item(), delivered({ id: 22, serial_number: "SN-2" })]), "/api/v1/organizations": json([]),
    });
    expect(await screen.findByText("SN-1")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Deliver/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Consume/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Undo/ })).not.toBeInTheDocument();
  });

  it("shows the markup rules without edit controls", async () => {
    go("/procurement/markup", "read_only", READ, {
      "/api/v1/procurement/markup-rules": json([{ id: 1, product_id: null, category: "hardware", markup_bp: 1500, created_at: TS, updated_at: TS }]),
      "/api/v1/settings": json({ default_markup_bp: 0 }),
    });
    expect(await screen.findByText("15.00%")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Edit/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add rule" })).not.toBeInTheDocument();
  });
});

describe("inventory", () => {
  it("shows the already invoiced error when an undo is refused", async () => {
    go("/procurement/inventory", "admin", WRITE, {
      "/api/v1/procurement/inventory": json([delivered()]), "/api/v1/organizations": json([]),
      "POST /api/v1/procurement/inventory/21/undo-delivery": json({ detail: "The charge is already invoiced; issue a credit memo instead" }, 409),
    });
    fireEvent.click(await screen.findByRole("button", { name: "Undo delivery of Laptop SN-1" }));
    fireEvent.click(await screen.findByRole("button", { name: "Confirm undo" }));
    expect(await screen.findByText(/already invoiced/)).toBeInTheDocument();
    expect(called("POST /api/v1/procurement/inventory/21/undo-delivery")).toBe(true);
  });

  it("shows an empty state", async () => {
    go("/procurement/inventory", "admin", WRITE, { "/api/v1/procurement/inventory": json([]), "/api/v1/organizations": json([]) });
    expect(await screen.findByText(/No inventory matches/)).toBeInTheDocument();
  });
});

describe("client inventory card", () => {
  it("lists the client's items on the organization page", async () => {
    go("/organizations/3", "read_only", READ, {
      "/api/v1/organizations/3": json({ id: 3, name: "Acme", status: "active", billing_address: null, notes: null, assets_published: false, archived_at: null }),
      "/api/v1/organizations/3/sites?include_archived=true": json([]),
      "/api/v1/organizations/3/contacts?include_archived=true": json([]),
      "/api/v1/procurement/organizations/3/inventory": json([delivered(), delivered({ id: 22, description: "Dock", serial_number: null, status: "in_stock", delivered_on: null, asset_id: null })]),
    });
    expect(await screen.findByText("Hardware and inventory")).toBeInTheDocument();
    expect(await screen.findByText("SN-1")).toBeInTheDocument();
    expect(screen.getByText("Dock")).toBeInTheDocument();
    expect(screen.getByText("2026-10-03")).toBeInTheDocument();
  });
});
