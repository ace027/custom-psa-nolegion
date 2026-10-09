import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";

const me = { id: 1, email: "t@example.com", display_name: "Terry Tech", role: "tech", permissions: ["org:read", "org:write", "user:read"] };

function route(handlers: Record<string, () => Response>) {
  vi.stubGlobal("fetch", vi.fn((url: string) => Promise.resolve(handlers[url]?.() ?? new Response("{}", { status: 404 }))));
}
const json = (body: unknown, status = 200) => () => new Response(JSON.stringify(body), { status });

function renderApp(path = "/organizations") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("App", () => {
  it("shows the sign-in page when unauthenticated", async () => {
    route({ "/api/auth/me": json({ detail: "Not authenticated" }, 401) });
    renderApp();
    expect(await screen.findByText("Sign in with Microsoft")).toBeInTheDocument();
  });

  it("hides admin-only navigation from a tech", async () => {
    route({
      "/api/auth/me": json(me),
      "/api/organizations?limit=200&include_archived=false&q=": json({ items: [{ id: 1, name: "Acme", status: "active", archived_at: null }], total: 1, limit: 200, offset: 0 }),
    });
    renderApp();
    expect(await screen.findByText("Acme")).toBeInTheDocument();
    expect(screen.queryByText("Audit log")).not.toBeInTheDocument();
    expect(screen.getByText("New organization")).toBeInTheDocument(); // techs may write
  });

  it("hides write controls from read-only users", async () => {
    route({
      "/api/auth/me": json({ ...me, role: "read_only", permissions: ["org:read", "user:read"] }),
      "/api/organizations?limit=200&include_archived=false&q=": json({ items: [], total: 0, limit: 200, offset: 0 }),
    });
    renderApp();
    expect(await screen.findByText("No organizations.")).toBeInTheDocument();
    expect(screen.queryByText("New organization")).not.toBeInTheDocument();
  });
});
