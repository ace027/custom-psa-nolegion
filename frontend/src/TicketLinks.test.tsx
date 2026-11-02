import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";

const json = (body: unknown) => new Response(JSON.stringify(body), { status: 200 });
const tk = (id: number, subject: string, over = {}) => ({
  id, number: 10000 + id, organization_id: 1, organization_name: "Acme", contact_id: null, contact_name: null,
  site_id: null, queue_id: 1, queue_name: "Support", category_id: null, category_name: null,
  priority_id: 3, priority_name: "Normal", priority_rank: 3, status: "open", assignee_id: null,
  assignee_name: null, subject, description: "", source: "ui", requester_email: null, needs_triage: false,
  sla_state: "ok", sla_first_response_due: null, sla_resolution_due: null, first_responded_at: null,
  created_at: "2026-09-30T12:00:00Z", updated_at: "2026-09-30T12:00:00Z", ...over,
});
const ALL = [tk(7, "Current"), tk(8, "Printer down"), tk(9, "VPN broken"), tk(10, "Old closed issue", { status: "closed" })];

function run(entries = ["/tickets/7"]) {
  const calls: { url: string; init?: RequestInit }[] = [];
  vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => {
    calls.push({ url, init });
    const u = new URL(url, "http://x");
    const p = u.pathname;
    if (p === "/api/v1/auth/me") return Promise.resolve(json({ id: 1, email: "u@e.com", display_name: "U", role: "tech", permissions: ["ticket:read", "ticket:write"] }));
    if (p === "/api/v1/tickets/7") return Promise.resolve(json(ALL[0]));
    if (p === "/api/v1/tickets") {
      const q = u.searchParams.get("q");
      const items = ALL.filter((t) => (u.searchParams.get("open_only") ? t.status !== "closed" : true)
        && (!q || String(t.number).includes(q) || t.subject.toLowerCase().includes(q.toLowerCase())));
      return Promise.resolve(json({ items, total: items.length, limit: 20, offset: 0 }));
    }
    if (p === "/api/v1/tickets/7/links" && init?.method === "POST") return Promise.resolve(json({}));
    if (p.endsWith("/links") || p.endsWith("/notes") || p.endsWith("/time") || p.endsWith("/attachments")) return Promise.resolve(json([]));
    return Promise.resolve(new Response("{}", { status: 404 }));
  }));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={entries}><App /></MemoryRouter>
    </QueryClientProvider>,
  );
  return calls;
}

afterEach(() => vi.unstubAllGlobals());

describe("ticket back control", () => {
  it("goes to the tickets list when there is no in-app history", async () => {
    run();
    fireEvent.click(await screen.findByRole("button", { name: "Back" }));
    expect(await screen.findByRole("heading", { name: /tickets/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Back" })).not.toBeInTheDocument();
  });
});

describe("ticket link picker", () => {
  it("filters by number and title, toggles closed, and posts the chosen link", async () => {
    const calls = run();
    const box = await screen.findByRole("combobox", { name: /search tickets/i });
    fireEvent.focus(box);
    expect(box).toHaveAttribute("aria-expanded", "true");
    expect(await screen.findByRole("option", { name: "#10008 — Printer down" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: /Current/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("option", { name: /Old closed/ })).not.toBeInTheDocument();

    fireEvent.click(screen.getByLabelText("Show closed tickets"));
    expect(await screen.findByRole("option", { name: /Old closed issue/ })).toBeInTheDocument();
    expect(calls.some((c) => c.url.includes("/tickets?") && !c.url.includes("open_only"))).toBe(true);

    fireEvent.change(box, { target: { value: "vpn" } });
    expect(await screen.findByRole("option", { name: "#10009 — VPN broken" })).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole("option", { name: /Printer/ })).not.toBeInTheDocument());

    fireEvent.change(box, { target: { value: "10010" } });
    const list = screen.getByRole("listbox");
    await waitFor(() => expect(within(list).getByRole("option")).toHaveTextContent("Old closed issue"));

    fireEvent.keyDown(box, { key: "ArrowDown" });
    fireEvent.keyDown(box, { key: "Enter" });
    expect(box).toHaveValue("#10010 — Old closed issue");
    fireEvent.click(screen.getByRole("button", { name: "Link" }));
    await waitFor(() => {
      const post = calls.find((c) => c.url.endsWith("/tickets/7/links") && c.init?.method === "POST");
      expect(JSON.parse(String(post?.init?.body))).toEqual({ relation: "related", other_number: 10010 });
    });
  });

  it("shows an empty state", async () => {
    run();
    const box = await screen.findByRole("combobox", { name: /search tickets/i });
    fireEvent.change(box, { target: { value: "zzz" } });
    expect(await screen.findByText("No matching tickets")).toBeInTheDocument();
    fireEvent.keyDown(box, { key: "Escape" });
    expect(box).toHaveAttribute("aria-expanded", "false");
  });
});
