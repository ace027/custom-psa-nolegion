import { fireEvent, render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { BRAND, applyBrand } from "./branding";
import { ClientScopeProvider, clientApiPath, clientRoute, useClientScope } from "./clientScope";
import OrganizationDetail from "./pages/OrganizationDetail";
import UtilisationReport from "./pages/reports/UtilisationReport";
import { NotesCard } from "./pages/TicketDetail";
import type { Note, Ticket } from "./api";

describe("branding", () => {
  it("has PSA defaults", () => {
    expect(BRAND.name).toBe("PSA");
    expect(BRAND.mark).toBe("P");
    expect(BRAND.logoUrl).toBeNull();
  });
  it("applies title and colour overrides", () => {
    applyBrand(document, { name: "Acme", mark: "A", logoUrl: null, colors: { "blue-600": "#ff0000" } });
    expect(document.title).toBe("Acme");
    expect(document.documentElement.style.getPropertyValue("--color-blue-600")).toBe("#ff0000");
  });
  it("ignores invalid colour JSON with a warning", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    vi.stubEnv("VITE_BRAND_COLORS", "{nope");
    vi.resetModules();
    const mod = await import("./branding");
    expect(mod.BRAND.colors).toEqual({});
    expect(warn).toHaveBeenCalled();
    vi.unstubAllEnvs();
    warn.mockRestore();
  });
});

describe("clientScope", () => {
  it("builds api paths and routes", () => {
    expect(clientApiPath(5)).toBe("/organizations/5");
    expect(clientApiPath(5, "billing", "rates", 3)).toBe("/organizations/5/billing/rates/3");
    expect(clientRoute(7)).toBe("/organizations/7");
  });
  function Probe() {
    const s = useClientScope();
    return <p>{String(s.orgId)}|{s.orgId === null ? "" : `${s.apiPath("sites")}|${s.route("x")}`}</p>;
  }
  const at = (path: string, provider?: number) =>
    render(
      <MemoryRouter initialEntries={[path]}>
        <ClientScopeProvider value={provider ?? null}>
          <Routes><Route path="*" element={<Probe />} /></Routes>
        </ClientScopeProvider>
      </MemoryRouter>,
    );
  it("resolves the id from /organizations/:id and /organizations/:id/*", () => {
    const { unmount } = at("/organizations/7");
    expect(screen.getByText("7|/organizations/7/sites|/organizations/7/x")).toBeInTheDocument();
    unmount();
    at("/organizations/7/anything");
    expect(screen.getByText("7|/organizations/7/sites|/organizations/7/x")).toBeInTheDocument();
  });
  it("is null on ticket and project routes without a provider", () => {
    const { unmount } = at("/tickets/7");
    expect(screen.getByText("null|")).toBeInTheDocument();
    unmount();
    at("/projects/7");
    expect(screen.getByText("null|")).toBeInTheDocument();
  });
  it("uses the provider value off client routes, even on ticket pages", () => {
    at("/tickets/7", 9);
    expect(screen.getByText("9|/organizations/9/sites|/organizations/9/x")).toBeInTheDocument();
  });
  it("lets the client route win over the provider", () => {
    at("/organizations/4", 9);
    expect(screen.getByText("4|/organizations/4/sites|/organizations/4/x")).toBeInTheDocument();
  });
  it("throws from apiPath and route when no client is in scope", () => {
    let scope!: ReturnType<typeof useClientScope>;
    function Grab() { scope = useClientScope(); return null; }
    render(<MemoryRouter initialEntries={["/tickets/7"]}><Grab /></MemoryRouter>);
    expect(() => scope.apiPath("sites")).toThrow("No client in scope");
    expect(() => scope.route()).toThrow("No client in scope");
  });
});

describe("OrganizationDetail", () => {
  it("fetches the client from the route id", async () => {
    const urls: string[] = [];
    const f = vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      urls.push(String(input));
      return new Response("[]", { status: 200, headers: { "Content-Type": "application/json" } });
    });
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter initialEntries={["/organizations/12"]}>
          <Routes><Route path="/organizations/:id" element={<OrganizationDetail />} /></Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    await vi.waitFor(() => expect(urls).toContain("/api/v1/organizations/12"));
    expect(urls).toContain("/api/v1/organizations/12/sites?include_archived=true");
    f.mockRestore();
  });
});

const note = (id: number, author_type: Note["author_type"], body: string): Note => ({
  id, author_name: author_type === "human" ? "Sam" : null, author_email: null, author_type, visibility: "internal", source: "ui", body, created_at: "2026-10-01T12:00:00Z", email_status: null,
});
const ticket = { id: 1, number: 1, contact_name: null } as unknown as Ticket;

describe("notes by author", () => {
  it("filters and badges", () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <NotesCard ticket={ticket} notes={[note(1, "human", "hello"), note(2, "system", "auto closed"), note(3, "ai", "summary")]} canWrite={false} onDone={() => {}} />
      </QueryClientProvider>,
    );
    const list = screen.getByRole("list");
    expect(within(list).getByText("System")).toBeInTheDocument();
    expect(within(list).getByText("AI")).toBeInTheDocument();
    const human = screen.getByRole("button", { name: "Human (1)" });
    expect(screen.getByRole("button", { name: "All (3)" })).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(human);
    expect(human).toHaveAttribute("aria-pressed", "true");
    expect(screen.queryByText("auto closed")).not.toBeInTheDocument();
    expect(screen.getByText("hello")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "System (1)" }));
    expect(screen.queryByText("hello")).not.toBeInTheDocument();
    expect(screen.getByText("auto closed")).toBeInTheDocument();
  });
  it("shows an empty state when only system notes exist", () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <NotesCard ticket={ticket} notes={[note(2, "system", "auto closed")]} canWrite={false} onDone={() => {}} />
      </QueryClientProvider>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Human (0)" }));
    expect(screen.getByText("No human notes")).toBeInTheDocument();
  });
});

describe("utilisation automation column", () => {
  it("renders automation minutes", async () => {
    const tot = { capacity_minutes: 480, logged_minutes: 240, billable_minutes: 120, utilisation_bp: 5000, billable_bp: 2500 };
    const body = { range: { from: "2026-10-01", to: "2026-10-31" }, rows: [{ ...tot, user_id: 1, name: "Sam", automation_minutes: 90 }], totals: tot };
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(body), { status: 200, headers: { "content-type": "application/json" } })));
    render(<QueryClientProvider client={new QueryClient()}><MemoryRouter><UtilisationReport /></MemoryRouter></QueryClientProvider>);
    const th = await screen.findByRole("columnheader", { name: "Automation" });
    expect(th).toHaveAttribute("title", "Not counted in utilisation %");
    expect((await screen.findAllByText("1h 30m")).length).toBeGreaterThan(0);
    vi.unstubAllGlobals();
  });
});
