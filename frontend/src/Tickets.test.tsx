import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";

const json = (body: unknown, status = 200) => () => new Response(JSON.stringify(body), { status });
const perms = (role: string, permissions: string[]) => ({ id: 1, email: "u@example.com", display_name: "Una User", role, permissions });
const READ = ["org:read", "user:read", "ticket:read"];

const ticket = (over = {}) => ({
  id: 7, number: 10007, organization_id: 1, organization_name: "Acme", contact_id: null, contact_name: null,
  site_id: null, queue_id: 1, queue_name: "Support", category_id: null, category_name: null,
  priority_id: 3, priority_name: "Normal", priority_rank: 3, status: "open", assignee_id: null,
  assignee_name: null, subject: "Printer down", description: "It is jammed", source: "ui",
  requester_email: null, needs_triage: false, sla_state: "at_risk", sla_first_response_due: null,
  sla_resolution_due: null, first_responded_at: null, created_at: "2026-09-30T12:00:00Z",
  updated_at: "2026-09-30T12:00:00Z", ...over,
});
const base = {
  "/api/queues": json([{ id: 1, name: "Support", archived_at: null, is_default: true }]),
  "/api/categories": json([]),
  "/api/priorities": json([{ id: 3, name: "Normal", rank: 3, archived_at: null, is_default: true, first_response_minutes: 240, resolution_minutes: 1440 }]),
  "/api/work-types": json([{ id: 1, name: "Remote", archived_at: null }]),
  "/api/users": json([]),
  "/api/settings": json({ timezone: "America/Chicago", business_days: [0, 1, 2, 3, 4], business_start_minute: 480, business_end_minute: 1020, billing_increment_minutes: 15, sla_at_risk_percent: 25 }),
  "/api/tickets/7/notes": json([
    { id: 1, author_name: "Una User", author_email: null, visibility: "internal", source: "ui", body: "secret thought", created_at: "2026-09-30T12:05:00Z", email_status: null },
    { id: 2, author_name: null, author_email: "pat@acme.com", visibility: "customer", source: "email", body: "still broken", created_at: "2026-09-30T12:10:00Z", email_status: "received" },
  ]),
  "/api/tickets/7/time": json([{ id: 1, user_id: 1, work_type_id: 1, work_date: "2026-09-30", minutes_actual: 20, minutes_billable: 30, billable: true, note: null, voided_at: null }]),
  "/api/tickets/7/attachments": json([{ id: 5, filename: "report.pdf", size_bytes: 2048 }]),
};

function run(handlers: Record<string, () => Response>) {
  vi.stubGlobal("fetch", vi.fn((url: string) => Promise.resolve(handlers[url]?.() ?? new Response("{}", { status: 404 }))));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/tickets/7"]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("ticket page", () => {
  it("shows notes, time, attachments and the SLA badge for a tech", async () => {
    run({ ...base, "/api/auth/me": json(perms("tech", [...READ, "ticket:write", "time:write"])), "/api/tickets/7": json(ticket()) });
    expect(await screen.findByText(/#10007 Printer down/)).toBeInTheDocument();
    expect(screen.getByText("SLA at risk")).toBeInTheDocument();
    expect(screen.getByText("secret thought")).toBeInTheDocument();
    expect(screen.getByText(/internal note/)).toBeInTheDocument();
    expect(screen.getByText(/email from customer/)).toBeInTheDocument();
    expect(screen.getAllByText("30 min").length).toBeGreaterThan(0);
    expect(screen.getByText(/Total billable/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "report.pdf" })).toHaveAttribute("href", "/api/attachments/5/download");
    expect(screen.getByRole("button", { name: "Add note" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Log time" })).toBeInTheDocument();
  });

  it("hides write controls from read-only users", async () => {
    run({ ...base, "/api/auth/me": json(perms("read_only", READ)), "/api/tickets/7": json(ticket()) });
    expect(await screen.findByText(/#10007 Printer down/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add note" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Log time" })).not.toBeInTheDocument();
    expect(screen.getAllByRole("combobox")[0]).toBeDisabled(); // status select
  });

  it("shows the triage panel for unmatched tickets and blocks time logging", async () => {
    run({
      ...base,
      "/api/auth/me": json(perms("tech", [...READ, "ticket:write", "time:write"])),
      "/api/tickets/7": json(ticket({ organization_id: null, organization_name: null, needs_triage: true, requester_email: "stranger@x.com", source: "email" })),
      "/api/organizations?limit=200&include_archived=false&q=": json({ items: [{ id: 1, name: "Acme", status: "active", archived_at: null }], total: 1, limit: 200, offset: 0 }),
    });
    expect(await screen.findByText("Needs triage")).toBeInTheDocument();
    expect(screen.getByText("stranger@x.com")).toBeInTheDocument();
    expect(screen.getByText(/Assign an organization before logging time/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Log time" })).not.toBeInTheDocument();
  });
});

describe("dashboard and navigation", () => {
  it("lands on the dashboard with counts, and hides Settings from techs", async () => {
    const t = ticket({ sla_state: "breached" });
    vi.stubGlobal("fetch", vi.fn((url: string) => Promise.resolve(
      ({
        "/api/auth/me": json(perms("tech", [...READ, "ticket:write"])),
        "/api/dashboard": json({ my_open: [], unassigned: [t], sla_at_risk: [t], counts: { open: 4, mine: 0, unassigned: 1, sla_at_risk: 1, needs_triage: 2 } }),
      } as Record<string, () => Response>)[url]?.() ?? new Response("{}", { status: 404 }),
    )));
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={["/"]}>
          <App />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByText("Needs triage")).toBeInTheDocument();
    expect(screen.getAllByText("SLA breached").length).toBeGreaterThan(0);
    expect(screen.getByText("Nothing assigned to you.")).toBeInTheDocument();
    expect(screen.queryByText("Settings")).not.toBeInTheDocument();
  });
});
