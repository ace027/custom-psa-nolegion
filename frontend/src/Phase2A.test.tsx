import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { clock } from "./pages/TimerBar";
import { mondayOf } from "./pages/Timesheet";

const json = (body: unknown, status = 200) => () => new Response(JSON.stringify(body), { status });
const me = { id: 1, email: "u@example.com", display_name: "Una User", role: "tech", permissions: ["org:read", "user:read", "ticket:read", "ticket:write", "time:write"] };
const timer = {
  ticket_id: 5, ticket_number: 10005, ticket_subject: "New starter", work_type_id: 1, category_id: null, category_name: null,
  billable: true, note: null, started_at: new Date(Date.now() - 125_000).toISOString(), elapsed_seconds: 125,
};
const sheet = {
  user_id: 1, user_name: "Una User", week_start: "2026-10-05", week_end: "2026-10-11", total_minutes: 150, billable_minutes: 90, internal_minutes: 60,
  days: Array.from({ length: 7 }, (_, i) => ({ date: `2026-10-0${5 + i}`.replace("2026-10-010", "2026-10-10").replace("2026-10-011", "2026-10-11"), minutes: i === 0 ? 150 : 0, billable_minutes: 0 })),
  entries: [
    { kind: "ticket", id: 1, work_date: "2026-10-05", label: "#10005 New starter", detail: "Remote", ticket_id: 5, minutes_actual: 90, minutes_billable: 90, billable: true, note: null, invoiced: false },
    { kind: "internal", id: 2, work_date: "2026-10-05", label: "Training", detail: null, ticket_id: null, minutes_actual: 60, minutes_billable: 0, billable: false, note: "SC-900", invoiced: false },
  ],
};

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function mount(path: string, handlers: Record<string, (init?: RequestInit) => Response>) {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => Promise.resolve(handlers[url.split("?")[0]]?.(init) ?? new Response("[]", { status: 200 }))),
  );
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}><App /></MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("timer", () => {
  it("formats elapsed time", () => {
    expect(clock(125)).toBe("0:02:05");
    expect(clock(3661)).toBe("1:01:01");
    expect(clock(-5)).toBe("0:00:00");
  });

  it("shows the running timer on every page and stops it", async () => {
    const calls: string[] = [];
    mount("/timesheet", {
      "/api/auth/me": json(me),
      "/api/timesheet": json(sheet),
      "/api/timer": (init) => {
        if (init?.method === "DELETE") { calls.push("discard"); return new Response(null, { status: 204 }); }
        return new Response(JSON.stringify(timer));
      },
      "/api/timer/stop": () => { calls.push("stop"); return new Response(JSON.stringify({ kind: "ticket", id: 1, minutes: 3 })); },
    });
    const bar = await screen.findByRole("status", { name: "Running timer" });
    expect(bar).toHaveTextContent("#10005 New starter");
    fireEvent.click(screen.getByRole("button", { name: "Stop" }));
    await waitFor(() => expect(calls).toEqual(["stop"]));
  });

  it("is hidden without a running timer or without time permission", async () => {
    mount("/dashboard", { "/api/auth/me": json({ ...me, permissions: ["org:read", "ticket:read"] }), "/api/timer": json(timer) });
    await screen.findByRole("link", { name: "Dashboard" });
    expect(screen.queryByRole("status", { name: "Running timer" })).toBeNull();
    expect(screen.queryByText("My timesheet")).toBeNull();
  });
});

describe("timesheet", () => {
  it("starts weeks on Monday", () => {
    expect(mondayOf(new Date(2026, 9, 11)).getDate()).toBe(5); // Sunday 11 Oct 2026
    expect(mondayOf(new Date(2026, 9, 5)).getDate()).toBe(5);
  });

  it("shows ticket and internal time and logs internal time", async () => {
    const posts: string[] = [];
    mount("/timesheet", {
      "/api/auth/me": json(me),
      "/api/timesheet": json(sheet),
      "/api/time-categories": json([{ id: 4, name: "Training", archived_at: null, is_default: false }]),
      "/api/internal-time": (init) => { posts.push(String(init?.body)); return new Response("{}", { status: 201 }); },
    });
    expect(await screen.findByText("#10005 New starter")).toBeInTheDocument();
    expect(screen.getByText("SC-900")).toBeInTheDocument();
    expect(screen.getByText(/Internal:/)).toHaveTextContent("1.00 h");
    await screen.findAllByRole("option", { name: "Training" });
    fireEvent.change(screen.getAllByLabelText("Category")[0], { target: { value: "4" } });
    fireEvent.change(screen.getByLabelText("Minutes"), { target: { value: "45" } });
    fireEvent.click(screen.getByRole("button", { name: "Add" }));
    await waitFor(() => expect(posts).toHaveLength(1));
    expect(JSON.parse(posts[0])).toMatchObject({ category_id: 4, minutes: 45 });
  });
});

describe("timesheet approval", () => {
  const admin = { ...me, role: "admin", permissions: [...me.permissions, "timesheet:approve"] };
  const row = { id: 9, user_id: 2, user_name: "Tess Tech", week_start: "2026-10-05", status: "submitted", submitted_at: null, approved_at: null, return_reason: null, total_minutes: 150 };

  it("lets the owner submit, and locks edits once submitted", async () => {
    const posts: string[] = [];
    vi.spyOn(window, "confirm").mockReturnValue(true);
    mount("/timesheet", {
      "/api/auth/me": json(me),
      "/api/timesheet": json(sheet),
      "/api/timesheet/submit": (init) => { posts.push(String(init?.body)); return new Response("{}"); },
    });
    fireEvent.click(await screen.findByRole("button", { name: "Submit week" }));
    await waitFor(() => expect(posts).toHaveLength(1));
    expect(JSON.parse(posts[0]).week_start).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });

  it("shows a submitted week as locked and a returned week with its reason", async () => {
    mount("/timesheet", { "/api/auth/me": json(me), "/api/timesheet": json({ ...sheet, status: "submitted" }) });
    await screen.findByText("#10005 New starter");
    expect(screen.queryByRole("button", { name: "Submit week" })).toBeNull();
    expect(screen.queryByText("Void")).toBeNull();
    expect(screen.queryByText("Log internal time")).toBeNull();
  });

  it("shows why a week was returned", async () => {
    mount("/timesheet", { "/api/auth/me": json(me), "/api/timesheet": json({ ...sheet, status: "returned", return_reason: "Missing Tuesday" }) });
    expect(await screen.findByRole("alert")).toHaveTextContent("Missing Tuesday");
    expect(screen.getByRole("button", { name: "Submit week" })).toBeInTheDocument();
  });

  it("gives admins the approval queue", async () => {
    const posts: string[] = [];
    mount("/timesheet", {
      "/api/auth/me": json(admin),
      "/api/timesheet": json(sheet),
      "/api/timesheets": json([row]),
      "/api/timesheet/approve": (init) => { posts.push(String(init?.body)); return new Response("{}"); },
    });
    expect(await screen.findByText("Tess Tech")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    await waitFor(() => expect(posts).toHaveLength(1));
    expect(JSON.parse(posts[0])).toEqual({ user_id: 2, week_start: "2026-10-05" });
    expect(screen.getByRole("link", { name: /Download hours CSV/ })).toHaveAttribute("href", expect.stringContaining("/api/timesheets/export.csv?from="));
  });

  it("hides approvals from people without the permission", async () => {
    mount("/timesheet", { "/api/auth/me": json(me), "/api/timesheet": json(sheet) });
    await screen.findByText("#10005 New starter");
    expect(screen.queryByText("Timesheet approvals")).toBeNull();
  });
});

describe("expenses", () => {
  const expense = {
    id: 3, user_id: 1, user_name: "Una User", expense_date: "2026-10-05", kind: "expense", category_id: 1, category_name: "Travel",
    description: "Parking", miles: null, mileage_rate_cents: null, amount_cents: 12345, reimbursable: true, billable: true, taxable: false,
    markup_bp: 1500, client_price_cents: 14197, organization_id: 1, organization_name: "Acme", ticket_id: null, invoiced: false,
    voided_at: null, receipts: [{ id: 8, filename: "p.png", content_type: "image/png", size_bytes: 3 }],
  };

  it("lists expenses with cost, billed price, markup and receipts", async () => {
    mount("/expenses", { "/api/auth/me": json(me), "/api/expenses": json([expense]), "/api/expense-categories": json([]), "/api/organizations": json([]) });
    expect(await screen.findByText("$123.45")).toBeInTheDocument();
    expect(screen.getByText(/\$141\.97/)).toBeInTheDocument();
    expect(screen.getByText(/\+15%/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "p.png" })).toHaveAttribute("href", "/api/expense-receipts/8/download");
  });

  it("sends the amount in cents and the markup in basis points", async () => {
    const posts: string[] = [];
    mount("/expenses", {
      "/api/auth/me": json(me),
      "/api/expenses": (init) => {
        if (init?.method === "POST") { posts.push(String(init.body)); return new Response(JSON.stringify(expense), { status: 201 }); }
        return new Response("[]");
      },
      "/api/expense-categories": json([{ id: 1, name: "Travel", archived_at: null, is_default: false }]),
      "/api/organizations": json([{ id: 1, name: "Acme" }]),
    });
    await screen.findByRole("option", { name: "Acme" });
    await screen.findByRole("option", { name: "Travel" });
    fireEvent.change(screen.getByLabelText("Amount ($)"), { target: { value: "123.45" } });
    fireEvent.change(screen.getByLabelText("Category"), { target: { value: "1" } });
    fireEvent.change(screen.getByLabelText("Description"), { target: { value: "Parking" } });
    fireEvent.change(screen.getByLabelText("Client (optional)"), { target: { value: "1" } });
    fireEvent.click(screen.getByLabelText("Bill to client"));
    fireEvent.change(await screen.findByLabelText("Markup %"), { target: { value: "15" } });
    fireEvent.click(screen.getByRole("button", { name: "Add expense" }));
    await waitFor(() => expect(posts).toHaveLength(1));
    expect(JSON.parse(posts[0])).toMatchObject({ kind: "expense", amount_cents: 12345, markup_bp: 1500, billable: true, organization_id: 1, category_id: 1 });
  });

  it("refuses a bad amount before calling the API", async () => {
    const posts: string[] = [];
    mount("/expenses", {
      "/api/auth/me": json(me),
      "/api/expenses": (init) => { if (init?.method === "POST") posts.push("x"); return new Response("[]"); },
      "/api/expense-categories": json([{ id: 1, name: "Travel", archived_at: null, is_default: false }]),
      "/api/organizations": json([]),
    });
    await screen.findByRole("option", { name: "Travel" });
    fireEvent.change(screen.getByLabelText("Amount ($)"), { target: { value: "abc" } });
    fireEvent.change(screen.getByLabelText("Category"), { target: { value: "1" } });
    fireEvent.change(screen.getByLabelText("Description"), { target: { value: "x" } });
    fireEvent.click(screen.getByRole("button", { name: "Add expense" }));
    expect(await screen.findByText("Enter the amount, like 24.99")).toBeInTheDocument();
    expect(posts).toHaveLength(0);
  });

  it("hides the page from people who cannot log time", async () => {
    mount("/dashboard", { "/api/auth/me": json({ ...me, permissions: ["org:read", "ticket:read"] }) });
    await screen.findByRole("link", { name: "Dashboard" });
    expect(screen.queryByText("My expenses")).toBeNull();
  });
});
