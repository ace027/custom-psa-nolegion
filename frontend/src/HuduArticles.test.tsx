import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import HuduArticlesCard from "./pages/HuduArticlesCard";

function card(body: unknown, { isAdmin = false, status = 200, pending = false } = {}) {
  vi.stubGlobal("fetch", vi.fn((url: string) => {
    expect(url).toBe("/api/v1/tickets/3/hudu-articles");
    return pending ? new Promise(() => {}) : Promise.resolve(new Response(JSON.stringify(body), { status }));
  }));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={qc}><MemoryRouter><HuduArticlesCard ticketId={3} isAdmin={isAdmin} /></MemoryRouter></QueryClientProvider>);
}
const ok = (articles: unknown[]) => ({ configured: true, articles, error: null });
afterEach(() => vi.unstubAllGlobals());

describe("Hudu articles card", () => {
  it("shows loading", () => {
    card(null, { pending: true });
    expect(screen.getByText("Loading…")).toBeInTheDocument();
  });

  it("lists articles as new-tab links with scope badges and dates", async () => {
    card(ok([
      { id: "1", title: "Printer offline", url: "https://hudu.example.com/a/1", updated_at: "2026-10-01T12:00:00Z", scope: "client" },
      { id: "2", title: "VPN checklist", url: "https://hudu.example.com/a/2", updated_at: null, scope: "global" },
    ]));
    const link = await screen.findByRole("link", { name: "Printer offline" });
    expect(link).toHaveAttribute("href", "https://hudu.example.com/a/1");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
    expect(screen.getByText("Client")).toBeInTheDocument();
    expect(screen.getByText("Global")).toBeInTheDocument();
    expect(screen.getAllByText(/^Updated /)).toHaveLength(1);
  });

  it("shows the empty state", async () => {
    card(ok([]));
    expect(await screen.findByText("No related Hudu articles")).toBeInTheDocument();
  });

  it("shows a Hudu error", async () => {
    card({ configured: true, articles: [], error: "Hudu request failed: ReadTimeout" });
    expect(await screen.findByRole("alert")).toHaveTextContent("Hudu request failed: ReadTimeout");
    expect(screen.queryByText("No related Hudu articles")).not.toBeInTheDocument();
  });

  it("shows a request error", async () => {
    card({ detail: "Ticket not found" }, { status: 404 });
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });

  it("not configured: links to Integrations for admins only", async () => {
    card({ configured: false, articles: [], error: null }, { isAdmin: true });
    expect(await screen.findByRole("link", { name: /Connect Hudu on the Integrations page/ })).toHaveAttribute("href", "/integrations");
  });

  it("not configured: plain text for everyone else", async () => {
    card({ configured: false, articles: [], error: null });
    expect(await screen.findByText(/Connect Hudu on the Integrations page to see related articles/)).toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });
});
