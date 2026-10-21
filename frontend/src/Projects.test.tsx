import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";

const json = (body: unknown, status = 200) => () => new Response(JSON.stringify(body), { status });
const STAFF = ["org:read", "ticket:read", "project:write", "billing:read", "billing:write"];
const TECH = ["org:read", "ticket:read", "project:write"];
const READ_ONLY = ["org:read", "ticket:read"];
const me = (role: string, permissions: string[]) => ({ id: 1, email: "u@example.com", display_name: "Una", role, permissions });
const ORGS = "/api/organizations?limit=200&include_archived=false&q=";
const orgs = json({ items: [{ id: 3, name: "Acme", status: "active" }], total: 1, limit: 200, offset: 0 });
const STATUSES = json([
  { id: 1, name: "New", behavior: "new", position: 1, archived_at: null },
  { id: 2, name: "In progress", behavior: "open", position: 2, archived_at: null },
  { id: 3, name: "Waiting", behavior: "waiting_on_customer", position: 3, archived_at: null },
  { id: 4, name: "Done", behavior: "resolved", position: 4, archived_at: null },
]);

const budget = (over = {}) => ({
  estimate_minutes: 600, actual_minutes: 300, billable_minutes: 300, cost_at_rates_cents: 75000, billed_cents: 0, remaining_cents: 100000, over_budget: false, ...over,
});
const summary = (over = {}) => ({
  id: 1, organization_id: 3, organization_name: "Acme", name: "Office move", description: null, status: "active", start_date: null, due_date: null, owner_id: null,
  approved_at: "2026-10-01T12:00:00Z", billing_mode: "tm", fixed_fee_cents: null, budget_cents: 100000, taxable: false, fixed_fee_billed: false, task_count: 2, done_count: 0,
  created_at: "2026-10-01T12:00:00Z", updated_at: "2026-10-01T12:00:00Z", ...over,
});
const task = (over = {}) => ({
  id: 10, project_id: 1, ticket_id: 101, ticket_number: 501, title: "Rack servers", status: "new", status_name: "New", assignee_id: null, assignee_name: null, phase_id: 7,
  estimate_minutes: 120, actual_minutes: 30, start_date: null, due_date: "2026-11-01", position: 0, depends_on: [], blocked: false, ...over,
});
const t1 = task();
const t2 = task({ id: 11, ticket_id: 102, ticket_number: 502, title: "Cable up", depends_on: [10], blocked: true, status: "open", status_name: "Open" });
const project = (over = {}) => ({
  ...summary(), approved_by_id: 1,
  phases: [{ id: 7, project_id: 1, name: "Build", position: 0, due_date: null, completed_at: null, task_count: 2 }],
  tasks: [t1, t2], budget: budget(), ...over,
});

let calls: string[] = [];
function go(path: string, role: string, perms: string[], h: Record<string, () => Response>) {
  const handlers: Record<string, () => Response> = { "/api/auth/me": json(me(role, perms)), ...h };
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

describe("projects list", () => {
  it("shows budget columns, over-budget warning and filters by status", async () => {
    go("/projects", "admin", STAFF, {
      [ORGS]: orgs,
      "/api/projects": json([summary(), summary({ id: 2, name: "Fixed job", billing_mode: "fixed_fee", fixed_fee_cents: 250000, budget_cents: null })]),
      "/api/projects?status=draft": json([]),
      "/api/projects/1/budget": json(budget()),
      "/api/projects/2/budget": json(budget({ remaining_cents: null, over_budget: true })),
    });
    const row = (await screen.findByRole("link", { name: "Office move" })).closest("tr")!;
    expect(await within(row).findByText("5.0 h")).toBeInTheDocument();
    expect(within(row).getAllByText("$1,000.00")).toHaveLength(2); // budget, remaining
    expect(await within(row).findByText("Time & materials")).toBeInTheDocument();
    const row2 = screen.getByRole("link", { name: "Fixed job" }).closest("tr")!;
    expect(within(row2).getByText("$2,500.00")).toBeInTheDocument();
    expect(await within(row2).findByText("Over budget")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "draft" } });
    expect(await screen.findByText("No projects yet.")).toBeInTheDocument();
  });

  it("creates a project with billing fields for someone who can bill", async () => {
    go("/projects", "admin", STAFF, {
      [ORGS]: orgs,
      "/api/projects": json([]),
      "POST /api/projects": json(project({ tasks: [], phases: [], task_count: 0 }), 201),
      "/api/projects/1": json(project({ tasks: [], phases: [], task_count: 0 })),
    });
    await screen.findByText("New project");
    await screen.findAllByRole("option", { name: "Acme" });
    fireEvent.change(screen.getByLabelText("Project client"), { target: { value: "3" } });
    fireEvent.change(screen.getByLabelText("Project name"), { target: { value: "Office move" } });
    fireEvent.change(screen.getByLabelText("Billing mode"), { target: { value: "fixed_fee" } });
    fireEvent.change(screen.getByLabelText("Fixed fee ($)"), { target: { value: "2500.00" } });
    fireEvent.click(screen.getByRole("button", { name: "Create project" }));
    await waitFor(() => expect(called("POST /api/projects ", '"fixed_fee_cents":250000')).toBe(true));
    expect(called("POST /api/projects ", '"organization_id":3')).toBe(true);
    expect(await screen.findByRole("heading", { name: "Office move" })).toBeInTheDocument();
  });

  it("hides billing fields from a tech and the form from read-only users", async () => {
    const view = go("/projects", "tech", TECH, { [ORGS]: orgs, "/api/projects": json([]) });
    await screen.findByText("New project");
    expect(screen.queryByLabelText("Billing mode")).toBeNull();
    view.unmount();
    go("/projects", "read_only", READ_ONLY, { [ORGS]: orgs, "/api/projects": json([]) });
    await screen.findByText("No projects yet.");
    expect(screen.queryByText("New project")).toBeNull();
  });
});

describe("project detail", () => {
  it("shows an empty state and adds a task", async () => {
    go("/projects/1", "admin", STAFF, {
      "/api/projects/1": json(project({ tasks: [], phases: [], task_count: 0 })),
      "POST /api/projects/1/tasks": json(task(), 201),
    });
    expect(await screen.findByText(/no phases or tasks yet/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Add task" }));
    fireEvent.change(screen.getByLabelText("Task title"), { target: { value: "Rack servers" } });
    fireEvent.change(screen.getByLabelText("Estimate (hours)"), { target: { value: "2.5" } });
    fireEvent.click(screen.getByRole("button", { name: "Add task to project" }));
    await waitFor(() => expect(called("POST /api/projects/1/tasks ", '"estimate_minutes":150')).toBe(true));
    expect(called("POST /api/projects/1/tasks ", '"title":"Rack servers"')).toBe(true);
  });

  it("shows blocked tasks and a dependency loop error inline", async () => {
    go("/projects/1", "admin", STAFF, {
      "/api/projects/1": json(project()),
      "PATCH /api/projects/1/tasks/10": json(t1),
      "POST /api/projects/1/tasks/10/dependencies/11": json({ detail: "That dependency would make a loop" }, 409),
    });
    expect(await screen.findByText("Blocked")).toBeInTheDocument();
    expect(screen.getByText("Depends on #501")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Edit #501" }));
    fireEvent.click(screen.getByLabelText(/#502 Cable up/));
    fireEvent.click(screen.getByRole("button", { name: "Save task" }));
    expect(await screen.findByText("That dependency would make a loop")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });

  it("moves a board card by patching the ticket status", async () => {
    go("/projects/1", "admin", STAFF, {
      "/api/projects/1": json(project()),
      "/api/ticket-statuses": STATUSES,
      "PATCH /api/tickets/101": json({}),
    });
    fireEvent.click(await screen.findByRole("tab", { name: "Board" }));
    const newCol = screen.getByRole("region", { name: "New" });
    expect(within(newCol).getByText("#501")).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "Open" })).getByText("Blocked")).toBeInTheDocument();
    expect(within(newCol).getByText("Due 2026-11-01")).toBeInTheDocument();
    await screen.findByRole("region", { name: "Resolved" });
    await waitFor(() => expect(called("/api/ticket-statuses")).toBe(true));
    fireEvent.change(within(newCol).getByLabelText("Move #501"), { target: { value: "resolved" } });
    await waitFor(() => expect(called("PATCH /api/tickets/101 ", '"status_id":4')).toBe(true));
  });

  it("budget tab warns when over budget", async () => {
    go("/projects/1", "admin", STAFF, {
      "/api/projects/1": json(project({ budget: budget({ over_budget: true, remaining_cents: 0, cost_at_rates_cents: 130000, billed_cents: 100000 }) })),
    });
    fireEvent.click(await screen.findByRole("tab", { name: "Budget" }));
    expect(screen.getByRole("alert")).toHaveTextContent(/Over budget/);
    expect(screen.getByText("$1,300.00", { selector: "div" })).toBeInTheDocument();
    expect(screen.getByText("Remaining").previousSibling).toHaveTextContent("$0.00");
  });

  it("offers Bill fixed fee now until billed, then says it was billed", async () => {
    const fixed = { billing_mode: "fixed_fee", fixed_fee_cents: 250000, budget_cents: null };
    const view = go("/projects/1", "admin", STAFF, {
      "/api/projects/1": json(project(fixed)),
      "POST /api/projects/1/bill-fixed-fee": json({}),
    });
    fireEvent.click(await screen.findByRole("button", { name: "Bill fixed fee now" }));
    await waitFor(() => expect(called("POST /api/projects/1/bill-fixed-fee")).toBe(true));
    view.unmount();
    go("/projects/1", "admin", STAFF, { "/api/projects/1": json(project({ ...fixed, fixed_fee_billed: true })) });
    expect(await screen.findByText("Fixed fee billed")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Bill fixed fee now" })).toBeNull();
  });

  it("draft projects need billing:write to approve", async () => {
    const draft = project({ status: "draft", approved_at: null });
    const view = go("/projects/1", "admin", STAFF, { "/api/projects/1": json(draft), "POST /api/projects/1/approve": json(project()) });
    fireEvent.click(await screen.findByRole("button", { name: "Approve" }));
    await waitFor(() => expect(called("POST /api/projects/1/approve")).toBe(true));
    view.unmount();
    go("/projects/1", "tech", TECH, { "/api/projects/1": json(draft) });
    await screen.findByRole("heading", { name: "Office move" });
    expect(screen.queryByRole("button", { name: "Approve" })).toBeNull();
    expect(screen.getByRole("button", { name: "Add task" })).toBeInTheDocument();
  });

  it("read-only users see no write controls", async () => {
    go("/projects/1", "read_only", READ_ONLY, { "/api/projects/1": json(project()), "/api/ticket-statuses": STATUSES });
    await screen.findByRole("heading", { name: "Office move" });
    expect(screen.queryByRole("button", { name: "Add task" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Edit #501" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Put on hold" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Approve" })).toBeNull();
    fireEvent.click(screen.getByRole("tab", { name: "Board" }));
    expect(screen.queryByLabelText("Move #501")).toBeNull();
  });
});

describe("links to projects", () => {
  it("the client page lists its projects with remaining budget", async () => {
    go("/organizations/3", "admin", STAFF, {
      "/api/organizations/3": json({ id: 3, name: "Acme", status: "active", billing_address: null, notes: null, assets_published: false, archived_at: null }),
      "/api/projects?organization_id=3": json([summary()]),
      "/api/projects/1/budget": json(budget()),
    });
    const link = await screen.findByRole("link", { name: "Office move" });
    expect(link).toHaveAttribute("href", "/projects/1");
    expect(await screen.findByText("$1,000.00 remaining")).toBeInTheDocument();
  });

  it("a ticket in a project links to it", async () => {
    go("/tickets/101", "admin", STAFF, {
      "/api/tickets/101": json({
        id: 101, number: 501, organization_id: 3, organization_name: "Acme", subject: "Rack servers", status: "new", status_id: 1, status_name: "New", sla_state: "none",
        needs_triage: false, source: "portal", created_at: "2026-10-01T12:00:00Z", project_id: 1, project_name: "Office move",
      }),
    });
    const link = await screen.findByRole("link", { name: "Office move" });
    expect(link).toHaveAttribute("href", "/projects/1");
  });

  it("the nav link needs ticket:read", async () => {
    go("/projects", "x", [], { "/api/projects": json([]) });
    await waitFor(() => expect(screen.queryByRole("link", { name: "Projects" })).toBeNull());
  });
});
