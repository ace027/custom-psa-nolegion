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

afterEach(() => vi.unstubAllGlobals());

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
