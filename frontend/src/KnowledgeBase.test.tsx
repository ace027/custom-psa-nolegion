import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";

const json = (body: unknown, status = 200) => () => new Response(JSON.stringify(body), { status });
const WRITE = ["kb:read", "kb:write"];
const READ = ["kb:read"];
const me = (role: string, permissions: string[]) => ({ id: 1, email: "u@example.com", display_name: "Una", role, permissions });
const TS = "2026-10-01T12:00:00Z";
const summary = (over = {}) => ({ id: 5, title: "Reset a password", visibility: "client", status: "published", tags: ["password"], updated_at: TS, snippet: "Open the portal and choose reset.", ...over });
const article = (over = {}) => ({ ...summary(), body: "Step 1\nStep 2 <b>x</b>", created_by_name: "Una", updated_by_name: "Una", created_at: TS, ...over });
const page = (items: unknown[]) => ({ items, total: items.length, limit: 25, offset: 0 });

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
const LIST = "/api/v1/kb/articles?limit=25&offset=0";
beforeEach(() => { calls = []; });
afterEach(() => vi.unstubAllGlobals());

describe("staff knowledge base", () => {
  it("lists articles and sends q only from 2 characters", async () => {
    go("/kb", "admin", WRITE, {
      [LIST]: json(page([summary()])),
      "/api/v1/kb/articles?q=pass&limit=25&offset=0": json(page([summary({ id: 6, title: "Password policy" })])),
    });
    expect(await screen.findByRole("link", { name: "Reset a password" })).toHaveAttribute("href", "/kb/5");
    fireEvent.change(screen.getByLabelText("Search articles"), { target: { value: "p" } });
    await new Promise((r) => setTimeout(r, 450));
    expect(called("/api/v1/kb/articles?q=")).toBe(false);
    fireEvent.change(screen.getByLabelText("Search articles"), { target: { value: "pass" } });
    expect(await screen.findByRole("link", { name: "Password policy" })).toBeInTheDocument();
    expect(called("/api/v1/kb/articles?q=pass")).toBe(true);
  });

  it("hides New article from read_only users", async () => {
    go("/kb", "read_only", READ, { [LIST]: json(page([summary()])) });
    await screen.findByRole("link", { name: "Reset a password" });
    expect(screen.queryByRole("button", { name: "New article" })).not.toBeInTheDocument();
  });

  it("shows New article to writers", async () => {
    go("/kb", "tech", WRITE, { [LIST]: json(page([])) });
    expect(await screen.findByRole("button", { name: "New article" })).toBeInTheDocument();
    expect(await screen.findByText("No articles found.")).toBeInTheDocument();
  });

  it("creates an article with POST and shows API errors inline", async () => {
    go("/kb/new", "admin", WRITE, { "POST /api/v1/kb/articles": json({ detail: "Title already used" }, 409) });
    fireEvent.change(await screen.findByLabelText("Title"), { target: { value: "VPN setup" } });
    fireEvent.change(screen.getByLabelText("Body"), { target: { value: "Install it" } });
    fireEvent.change(screen.getByLabelText("Tags (comma separated)"), { target: { value: "vpn, Network" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Title already used")).toBeInTheDocument();
    expect(called("POST /api/v1/kb/articles", '"title":"VPN setup"')).toBe(true);
    expect(called("POST /api/v1/kb/articles", '"tags":["vpn","Network"]')).toBe(true);
  });

  it("renders the body as plain text and archives", async () => {
    go("/kb/5", "admin", WRITE, {
      "/api/v1/kb/articles/5": json(article()),
      "PATCH /api/v1/kb/articles/5": json(article({ status: "archived" })),
    });
    expect(await screen.findByText(/Step 2 <b>x<\/b>/)).toBeInTheDocument();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    fireEvent.click(screen.getByRole("button", { name: "Archive" }));
    await waitFor(() => expect(called("PATCH /api/v1/kb/articles/5", '"status":"archived"')).toBe(true));
  });

  it("offers no edit controls to read_only users", async () => {
    go("/kb/5", "read_only", READ, { "/api/v1/kb/articles/5": json(article()) });
    await screen.findByText(/Step 1/);
    expect(screen.queryByRole("button", { name: "Edit" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Archive" })).not.toBeInTheDocument();
  });
});

describe("ticket suggestions card", () => {
  async function card(items: unknown[]) {
    const { default: KbSuggestionsCard } = await import("./pages/KbSuggestionsCard");
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response(JSON.stringify(items), { status: 200 }))));
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={qc}><MemoryRouter><KbSuggestionsCard ticketId={3} /></MemoryRouter></QueryClientProvider>);
  }

  it("shows suggested articles with visibility", async () => {
    await card([summary(), summary({ id: 6, title: "Internal fix", visibility: "internal" })]);
    expect(await screen.findByRole("link", { name: "Reset a password" })).toHaveAttribute("href", "/kb/5");
    expect(screen.getByText("Internal")).toBeInTheDocument();
    expect(screen.getByText("Client")).toBeInTheDocument();
    expect(screen.getByText("Suggested articles")).toBeInTheDocument();
  });

  it("shows the empty state", async () => {
    await card([]);
    expect(await screen.findByText("No matching articles")).toBeInTheDocument();
  });
});

describe("portal knowledge base", () => {
  const portalMe = { contact_name: "Pat", organization_name: "Acme", company_name: null, can_see_billing: false, can_see_devices: false };
  const base = { "/api/v1/portal/me": json(portalMe) };

  it("lists help articles and searches with q", async () => {
    go("/portal/kb", "admin", [], {
      ...base,
      "/api/v1/portal/kb": json([{ id: 5, title: "Reset a password", tags: [], updated_at: TS, snippet: "s" }]),
      "/api/v1/portal/kb?q=pass": json([{ id: 6, title: "Password policy", tags: [], updated_at: TS, snippet: "s" }]),
    });
    expect(await screen.findByRole("link", { name: "Reset a password" })).toHaveAttribute("href", "/portal/kb/5");
    fireEvent.change(screen.getByLabelText("Search help articles"), { target: { value: "pass" } });
    expect(await screen.findByRole("link", { name: "Password policy" })).toBeInTheDocument();
  });

  it("shows an article body as text", async () => {
    go("/portal/kb/5", "admin", [], { ...base, "/api/v1/portal/kb/5": json({ id: 5, title: "Reset a password", body: "Line <i>one</i>", tags: [], updated_at: TS }) });
    expect(await screen.findByText("Line <i>one</i>")).toBeInTheDocument();
  });

  it("shows not found for a hidden article", async () => {
    go("/portal/kb/9", "admin", [], { ...base, "/api/v1/portal/kb/9": json({ detail: "Not found" }, 404) });
    expect(await screen.findByText("This article was not found.")).toBeInTheDocument();
  });
});
