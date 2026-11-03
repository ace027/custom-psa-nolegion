import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import Audit from "./Audit";

const ENTRY = {
  id: 1, occurred_at: "2026-01-02T10:00:00Z", actor_type: "user", actor_id: 7, action: "contact.update", entity_type: "contact", entity_id: 3,
  organization_id: null, before: { phone: "1" }, after: { phone: "2" }, detail: null, actor_name: "Ann", organization_name: null,
  summary: "Ann changed contact Bob", changes: [{ field: "phone", label: "Phone", before: "1", after: "2" }],
};

function setup(typesFail = false) {
  const urls: string[] = [];
  vi.stubGlobal("fetch", vi.fn((raw: string) => {
    urls.push(raw);
    const path = raw.split("?")[0];
    if (path === "/api/v1/audit/entity-types" && typesFail) return Promise.resolve(new Response(JSON.stringify({ detail: "types broke" }), { status: 500 }));
    const body = path === "/api/v1/audit" ? { items: [ENTRY, { ...ENTRY, id: 2, summary: "Ann signed in", changes: [] }], total: 2, limit: 50, offset: 0 }
      : path === "/api/v1/users" ? [{ id: 7, display_name: "Ann" }]
      : path === "/api/v1/audit/entity-types" ? [{ value: "contact", label: "Contact" }] : [];
    return Promise.resolve(new Response(JSON.stringify(body)));
  }));
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><Audit /></QueryClientProvider>);
  return urls;
}

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe("Audit page", () => {
  it("shows the sentence and change, raw JSON only after Show raw", async () => {
    setup();
    expect(await screen.findByText("Ann changed contact Bob")).toBeTruthy();
    expect(screen.getByText("Phone: 1 → 2")).toBeTruthy();
    expect(screen.queryByText(/"before"/)).toBeNull();
    fireEvent.click(screen.getAllByRole("button", { name: "Show raw" })[0]);
    expect(screen.getByText(/"before"/)).toBeTruthy();
  });

  it("sends actor_id and date_from when filters change", async () => {
    const urls = setup();
    await screen.findByText("Ann changed contact Bob");
    await screen.findByRole("option", { name: "Ann" });
    fireEvent.change(screen.getByLabelText("Person"), { target: { value: "7" } });
    fireEvent.change(screen.getByLabelText("From"), { target: { value: "2026-01-01" } });
    await waitFor(() => expect(urls.some((u) => u.includes("actor_id=7") && u.includes("date_from=2026-01-01"))).toBe(true));
  });

  it("renders entity type labels and sends the value as entity_type", async () => {
    const urls = setup();
    await screen.findByText("Ann changed contact Bob");
    await screen.findByRole("option", { name: "Contact" });
    fireEvent.change(screen.getByLabelText("Record type"), { target: { value: "contact" } });
    await waitFor(() => expect(urls.some((u) => u.includes("entity_type=contact"))).toBe(true));
  });

  it("keeps only Any and shows the error when entity types fail", async () => {
    setup(true);
    expect(await screen.findByText("types broke")).toBeTruthy();
    expect(screen.getByLabelText("Record type").querySelectorAll("option")).toHaveLength(1);
  });
});
