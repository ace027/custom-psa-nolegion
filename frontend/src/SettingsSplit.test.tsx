import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";

const ADMIN = [
  "ticket:read", "org:read", "user:read", "billing:read", "schedule:read", "crm:read", "quote:read", "service:configure", "config:manage",
  "invoice:read", "report:read", "audit:read", "user:manage",
];
const PERMS: Record<string, string[]> = {
  admin: ADMIN,
  manager: ["ticket:read", "org:read", "user:read", "billing:read", "schedule:read", "crm:read", "quote:read", "report:read", "audit:read", "invoice:read", "service:configure"],
  tech: ["ticket:read", "org:read", "user:read", "schedule:read"],
};

// Every card heading the old single Settings page had, and the sub-page that now holds it.
const PAGES: Record<string, string[]> = {
  "/admin/settings/mail": ["Mailbox connector", "Outlook calendar sync", "Appointment emails", "Auto-acknowledgement and escalation"],
  "/admin/settings/general": ["Business hours, SLA and billing", "Invoicing: your company details"],
  "/admin/settings/tickets": [
    "Queues", "Categories", "Work types", "Priorities and SLA targets (business minutes)", "Ticket statuses", "Ticket types and custom fields", "Canned responses",
  ],
  "/admin/settings/scheduling": ["Holidays"],
  "/admin/settings/billing": ["Payment reminders and statements", "Late fees", "Internal time categories", "Mileage rate", "Expense categories"],
  "/admin/settings/portal": ["Client portal"],
  "/admin/settings/sales": ["Sales", "Sales pipeline stages"],
};
const OLD_HEADINGS = [
  "Mailbox connector", "Outlook calendar sync", "Appointment emails", "Invoicing: your company details", "Payment reminders and statements", "Late fees",
  "Client portal", "Sales", "Sales pipeline stages", "Business hours, SLA and billing", "Ticket statuses", "Ticket types and custom fields", "Holidays",
  "Auto-acknowledgement and escalation", "Queues", "Categories", "Work types", "Internal time categories", "Mileage rate", "Expense categories",
  "Priorities and SLA targets (business minutes)", "Canned responses",
];

const SETTINGS = {
  timezone: "America/Chicago", business_days: [0, 1, 2, 3, 4], business_start_minute: 480, business_end_minute: 1020, billing_increment_minutes: 15,
  sla_at_risk_percent: 25, portal_enabled: false, auto_ack_enabled: false, auto_ack_subject: "Hi", auto_ack_body: "Body", escalation_email: null,
  escalation_bump_priority: false, csat_enabled: false, mileage_rate_cents: 67, company_name: null, company_address: null, invoice_footer: null,
  renewal_reminder_days: [90, 60, 30], renewal_email: null, appointment_emails_enabled: false,
};

function Where() {
  return <output data-testid="where">{useLocation().pathname}</output>;
}

function go(path: string, role: string, patches: string[] = []) {
  vi.stubGlobal(
    "fetch",
    vi.fn((raw: string, init?: RequestInit) => {
      const url = raw.split("?")[0];
      const method = init?.method ?? "GET";
      if (method === "PATCH" && url === "/api/v1/settings") patches.push(String(init?.body));
      const body =
        url === "/api/v1/auth/me" ? { id: 1, email: "u@example.com", display_name: "Una User", role, permissions: PERMS[role] }
        : url === "/api/v1/me/bookmarks" ? { items: null }
        : url === "/api/v1/settings" ? SETTINGS
        : url === "/api/v1/mail/status" ? { configured: false }
        : [];
      return Promise.resolve(new Response(JSON.stringify(body)));
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

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const cardHeadings = () => screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent);

describe("Settings split", () => {
  it("lists the old headings on exactly one sub-page each", () => {
    const all = Object.values(PAGES).flat();
    expect(all).toHaveLength(OLD_HEADINGS.length);
    expect([...all].sort()).toEqual([...OLD_HEADINGS].sort());
  });

  for (const [route, headings] of Object.entries(PAGES)) {
    it(`shows ${headings.length} card(s) on ${route}`, async () => {
      go(route, "admin");
      await waitFor(() => expect(cardHeadings().sort()).toEqual([...headings].sort()));
    });
  }

  it("shows a manager the Tickets and Scheduling settings only", async () => {
    go("/admin/settings", "manager");
    const sub = await screen.findByRole("navigation", { name: "Settings pages" });
    expect(within(sub).getAllByRole("link").map((a) => a.textContent)).toEqual(["Tickets", "Scheduling"]);
    for (const page of ["mail", "billing", "portal", "general", "sales"]) {
      cleanup();
      go(`/admin/settings/${page}`, "manager");
      await screen.findByRole("navigation", { name: "Settings pages" });
      await act(() => new Promise((r) => setTimeout(r, 0)));
      expect(screen.getByTestId("where")).toHaveTextContent(/^\/admin\/settings$/);
    }
    cleanup();
    go("/admin/settings/tickets", "manager");
    expect(await screen.findByRole("heading", { name: "Queues" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Canned responses" })).toBeNull(); // written under config:manage
  });

  it("gives a role with neither permission no Settings pages", async () => {
    go("/admin/settings", "tech");
    await screen.findByRole("navigation", { name: "Main" });
    await act(() => new Promise((r) => setTimeout(r, 0)));
    expect(screen.queryByRole("navigation", { name: "Settings pages" })).toBeNull();
    expect(screen.getByTestId("where")).toHaveTextContent(/^\/dashboard$/);
  });

  it("saves the time zone from General with the same request as before", async () => {
    const patches: string[] = [];
    go("/admin/settings/general", "admin", patches);
    const zone = await screen.findByLabelText("Time zone");
    fireEvent.change(zone, { target: { value: "America/New_York" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(patches).toHaveLength(1));
    expect(JSON.parse(patches[0])).toEqual({ ...SETTINGS, timezone: "America/New_York" });
  });
});
