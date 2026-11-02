import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { CAP_MESSAGE, SAVE_ERROR } from "./nav/useBookmarks";

const TECH = ["org:read", "user:read", "ticket:read", "billing:read", "quote:read", "schedule:read", "crm:read", "time:write"];

let puts: string[][] = [];

function go(saved: string[] | null, { failPut = false } = {}) {
  puts = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      if (url === "/api/v1/auth/me")
        return Promise.resolve(new Response(JSON.stringify({ id: 1, email: "t@example.com", display_name: "Terry Tech", role: "tech", permissions: TECH })));
      if (url === "/api/v1/me/bookmarks" && init?.method === "PUT") {
        const items = JSON.parse(String(init.body)).items as string[];
        puts.push(items);
        return Promise.resolve(failPut ? new Response('{"detail":"boom"}', { status: 500 }) : new Response(JSON.stringify({ items })));
      }
      if (url === "/api/v1/me/bookmarks") return Promise.resolve(new Response(JSON.stringify({ items: saved })));
      return Promise.resolve(new Response("{}", { status: 404 }));
    }),
  );
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/organizations"]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => vi.unstubAllGlobals());

const rail = () => screen.getByRole("list", { name: "Bookmarks" });
const railNames = () => within(rail()).getAllByRole("link").map((a) => a.getAttribute("aria-label") ?? a.textContent);
const link = (name: string) => within(rail()).getByRole("link", { name });
async function loaded(names: string[]) {
  await waitFor(() => expect(railNames()).toEqual(names));
}

describe("bookmarks", () => {
  it("shows the role defaults when nothing is saved", async () => {
    go(null);
    await loaded(["Tickets", "Dispatch", "My timesheet", "Organizations"]);
  });

  it("adds a starred page to the end and saves", async () => {
    go(["tickets", "dispatch"]);
    await loaded(["Tickets", "Dispatch"]);
    fireEvent.click(screen.getByRole("button", { name: "All pages" }));
    const star = screen.getByRole("button", { name: "Bookmark Projects" });
    expect(star).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(star);
    await loaded(["Tickets", "Dispatch", "Projects"]);
    expect(star).toHaveAttribute("aria-pressed", "true");
    expect(puts).toEqual([["tickets", "dispatch", "projects"]]);
  });

  it("stars the current page from the header", async () => {
    go(["tickets"]);
    await loaded(["Tickets"]);
    fireEvent.click(screen.getByRole("button", { name: "Bookmark this page" }));
    await loaded(["Tickets", "Organizations"]);
    expect(puts).toEqual([["tickets", "organizations"]]);
  });

  it("refuses a 9th bookmark with a message", async () => {
    const eight = ["dashboard", "tickets", "projects", "dispatch", "oncall", "timesheet", "expenses", "pipeline"];
    go(eight);
    await waitFor(() => expect(railNames()).toHaveLength(8));
    fireEvent.click(screen.getByRole("button", { name: "All pages" }));
    fireEvent.click(screen.getByRole("button", { name: "Bookmark Leads" }));
    expect(screen.getByText(CAP_MESSAGE)).toHaveAttribute("role", "status");
    expect(railNames()).toHaveLength(8);
    expect(puts).toEqual([]);
  });

  it("moves down from the menu, with Move up disabled at the top and Move down at the bottom", async () => {
    go(["tickets", "dispatch", "organizations"]);
    await loaded(["Tickets", "Dispatch", "Organizations"]);
    fireEvent.click(screen.getByRole("button", { name: "Options for Organizations" }));
    expect(screen.getByRole("menuitem", { name: "Move down" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Options for Organizations" })); // close
    fireEvent.click(screen.getByRole("button", { name: "Options for Tickets" }));
    expect(screen.getByRole("menuitem", { name: "Move up" })).toBeDisabled();
    fireEvent.click(screen.getByRole("menuitem", { name: "Move down" }));
    await loaded(["Dispatch", "Tickets", "Organizations"]);
    expect(puts).toEqual([["dispatch", "tickets", "organizations"]]);
    expect(screen.getByText("Tickets moved to position 2 of 3")).toBeInTheDocument();
  });

  it("moves with Alt+ArrowUp and keeps focus on the moved bookmark", async () => {
    go(["tickets", "dispatch", "organizations"]);
    await loaded(["Tickets", "Dispatch", "Organizations"]);
    link("Organizations").focus();
    fireEvent.keyDown(link("Organizations"), { key: "ArrowUp", altKey: true });
    await loaded(["Tickets", "Organizations", "Dispatch"]);
    expect(link("Organizations")).toHaveFocus();
    expect(puts).toEqual([["tickets", "organizations", "dispatch"]]);
    expect(screen.getByText("Organizations moved to position 2 of 3")).toBeInTheDocument();
    // the first item cannot move up
    link("Tickets").focus();
    fireEvent.keyDown(link("Tickets"), { key: "ArrowUp", altKey: true });
    expect(puts).toHaveLength(1);
  });

  it("moves on a drop", async () => {
    go(["tickets", "dispatch", "organizations"]);
    await loaded(["Tickets", "Dispatch", "Organizations"]);
    const dataTransfer = { setData: () => {}, getData: () => "", effectAllowed: "", dropEffect: "" };
    fireEvent.dragStart(screen.getByTestId("bookmark-tickets"), { dataTransfer });
    fireEvent.dragOver(screen.getByTestId("bookmark-organizations"), { dataTransfer });
    fireEvent.drop(screen.getByTestId("bookmark-organizations"), { dataTransfer });
    await loaded(["Dispatch", "Organizations", "Tickets"]);
    expect(puts).toEqual([["dispatch", "organizations", "tickets"]]);
  });

  it("restores the previous order and says so when saving fails", async () => {
    go(["tickets", "dispatch"], { failPut: true });
    await loaded(["Tickets", "Dispatch"]);
    link("Dispatch").focus();
    fireEvent.keyDown(link("Dispatch"), { key: "ArrowUp", altKey: true });
    expect(await screen.findByText(SAVE_ERROR)).toHaveAttribute("role", "alert");
    await loaded(["Tickets", "Dispatch"]);
    expect(puts).toEqual([["dispatch", "tickets"]]);
  });

  it("hides a page the role cannot open but keeps it in the saved list", async () => {
    go(["tickets", "invoices", "dispatch", "retired-page"]);
    await loaded(["Tickets", "Dispatch"]);
    link("Dispatch").focus();
    fireEvent.keyDown(link("Dispatch"), { key: "ArrowUp", altKey: true });
    await loaded(["Dispatch", "Tickets"]);
    expect(puts).toEqual([["dispatch", "invoices", "tickets", "retired-page"]]);
  });
});
