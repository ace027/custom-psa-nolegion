import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { NAV_ITEMS, allRoutes, canOpen } from "./nav/navConfig";

// Role permissions as in backend/app/permissions.py MATRIX (phase 16 split).
const READ = ["org:read", "user:read", "ticket:read", "billing:read", "quote:read", "schedule:read", "crm:read"];
const TECH = [...READ, "org:write", "ticket:write", "time:write", "charge:write", "quote:write", "schedule:write", "project:write", "crm:write"];
const PERMS: Record<string, string[]> = {
  read_only: READ,
  tech: TECH,
  manager: [...TECH, "timesheet:approve", "timeoff:approve", "report:read", "audit:read", "invoice:read", "service:configure"],
  billing: [...READ, "invoice:read", "procurement:read", "billing:write", "billing:finalize", "charge:write", "payment:write", "report:read", "procurement:write"],
  admin: [
    ...TECH, "invoice:read", "procurement:read", "procurement:write", "service:configure", "user:manage", "audit:read", "timesheet:approve", "config:manage",
    "portal:manage", "quote:manage", "integration:manage", "timeoff:approve", "apikey:manage", "automation:manage", "billing:write", "billing:finalize",
    "payment:write", "report:read",
  ],
};

const COMMON = ["Dashboard", "Tickets", "Projects", "Dispatch", "On-call", "Organizations", "Pipeline", "Leads", "Forecast", "Renewals", "Quotes", "Rate card"];
const FINANCE_INVOICES = ["Monthly runs", "Invoices", "Receivables", "Client emails", "Payments", "Credit memos", "Late fees", "Agreements", "Products", "Rates", "Billing reports"];
const PROCUREMENT = ["Orders and vendors", "Inventory", "Markup rules"];
const REPORTS = ["SLA report", "Utilisation report", "Aging report", "Profitability report", "Report schedules", "Warranty"];
const EXPECTED: Record<string, string[]> = {
  read_only: COMMON,
  tech: [...COMMON, "My timesheet", "My expenses"],
  manager: [...COMMON, "My timesheet", "My expenses", ...FINANCE_INVOICES, ...REPORTS, "Settings", "Audit log"],
  billing: [...COMMON, ...FINANCE_INVOICES, ...PROCUREMENT, ...REPORTS],
  admin: NAV_ITEMS.map((i) => i.label),
};

function Where() {
  const loc = useLocation();
  return <output data-testid="where">{loc.pathname}</output>;
}

function go(path: string, role: string) {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      const body =
        url === "/api/v1/auth/me"
          ? { id: 1, email: "u@example.com", display_name: "Una User", role, permissions: PERMS[role] }
          : url === "/api/v1/me/bookmarks"
            ? { items: null }
            : null;
      return Promise.resolve(body ? new Response(JSON.stringify(body)) : new Response("{}", { status: 404 }));
    }),
  );
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <App />
        <Where />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => vi.unstubAllGlobals());

// Wait for the app shell, then let <Navigate> effects run before reading the location.
async function settled() {
  await screen.findByRole("navigation", { name: "Main" });
  await act(() => new Promise((r) => setTimeout(r, 0)));
}

async function openAllPages() {
  fireEvent.click(await screen.findByRole("button", { name: "All pages" }));
  return screen.getByRole("region", { name: "All pages" });
}

describe("All pages by role", () => {
  for (const role of Object.keys(EXPECTED)) {
    it(`shows ${role} exactly the pages the role can open`, async () => {
      go("/organizations", role);
      const panel = await openAllPages();
      const shown = within(panel)
        .getAllByRole("button", { name: /^Bookmark / })
        .map((b) => b.getAttribute("aria-label")!.replace(/^Bookmark /, ""));
      expect([...shown].sort()).toEqual([...EXPECTED[role]].sort());
      const me = { permissions: PERMS[role] } as Parameters<typeof canOpen>[0];
      for (const label of shown) {
        const item = NAV_ITEMS.find((i) => i.label === label)!;
        expect(canOpen(me, item)).toBe(true);
      }
      const finance = within(panel).queryByRole("heading", { name: "Finance" });
      if (role === "tech" || role === "read_only") expect(finance).toBeNull();
      else expect(finance).not.toBeNull();
    });
  }
});

describe("routes", () => {
  it("registers every nav route", async () => {
    for (const route of allRoutes()) {
      const { unmount } = go(route, "admin");
      await settled();
      expect(screen.getByTestId("where")).toHaveTextContent(new RegExp(`^${route}$`));
      unmount();
    }
  });

  it.each([
    ["/settings", "/admin/settings"],
    ["/users", "/admin/users"],
    ["/kb", "/tickets"],
    ["/kb/123", "/tickets"],
  ])("redirects %s to %s", async (from, to) => {
    go(from, "admin");
    await settled();
    expect(screen.getByTestId("where")).toHaveTextContent(new RegExp(`^${to}$`));
  });

  it("gives Admin pages a sub-nav of the admin pages the role can open", async () => {
    go("/admin/users", "admin");
    const sub = await screen.findByRole("navigation", { name: "Admin" });
    expect(within(sub).getAllByRole("link").map((a) => a.textContent)).toEqual(
      NAV_ITEMS.filter((i) => i.section === "admin").map((i) => i.label),
    );
  });
});

describe("All pages panel", () => {
  it("closes on Esc and returns focus to its button", async () => {
    go("/organizations", "tech");
    const button = await screen.findByRole("button", { name: "All pages" });
    fireEvent.click(button);
    expect(button).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("region", { name: "All pages" })).toHaveFocus();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("region", { name: "All pages" })).toBeNull();
    expect(button).toHaveFocus();
    expect(button).toHaveAttribute("aria-expanded", "false");
  });
});
