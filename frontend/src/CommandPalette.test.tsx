import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";

const READ = ["org:read", "user:read", "ticket:read", "billing:read", "quote:read", "schedule:read", "crm:read"];
const TECH = [...READ, "org:write", "ticket:write", "time:write", "charge:write", "quote:write", "schedule:write", "project:write", "crm:write"];
const PERMS: Record<string, string[]> = {
  read_only: READ,
  tech: TECH,
  billing: [...READ, "invoice:read", "procurement:read", "billing:write", "payment:write", "report:read"],
  admin: [...TECH, "invoice:read", "procurement:read", "service:configure", "config:manage", "payment:write", "report:read"],
};

let puts: string[][] = [];

function Where() {
  return <output data-testid="where">{useLocation().pathname}</output>;
}

function go(role: string, saved: string[] | null = ["tickets", "dispatch"]) {
  puts = [];
  sessionStorage.clear();
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      if (url === "/api/v1/auth/me")
        return Promise.resolve(new Response(JSON.stringify({ id: 1, email: "u@example.com", display_name: "Una User", role, permissions: PERMS[role] })));
      if (url === "/api/v1/me/bookmarks" && init?.method === "PUT") {
        const items = JSON.parse(String(init.body)).items as string[];
        puts.push(items);
        return Promise.resolve(new Response(JSON.stringify({ items })));
      }
      if (url === "/api/v1/me/bookmarks") return Promise.resolve(new Response(JSON.stringify({ items: saved })));
      if (url === "/api/v1/tickets?q=123&limit=5")
        return Promise.resolve(new Response(JSON.stringify({ items: [{ id: 77, number: 123, subject: "Printer jam" }] })));
      return Promise.resolve(new Response("{}", { status: 404 }));
    }),
  );
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/organizations"]}>
        <App />
        <Where />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => vi.unstubAllGlobals());

const where = () => screen.getByTestId("where").textContent;
const dialog = () => screen.getByRole("dialog", { name: "Go to" });
const box = () => within(dialog()).getByRole("combobox");
const options = () => within(dialog()).queryAllByRole("option").map((o) => o.textContent ?? "");
async function ready() {
  await screen.findByRole("navigation", { name: "Main" });
  await screen.findByRole("link", { name: "Tickets" }); // bookmarks loaded
}
async function open(role: string, saved?: string[] | null) {
  go(role, saved);
  await ready();
  fireEvent.keyDown(document.body, { key: "k", ctrlKey: true });
  await screen.findByRole("dialog", { name: "Go to" });
}
const type = (text: string) => fireEvent.change(box(), { target: { value: text } });

describe("command palette", () => {
  it("opens on Ctrl+K and on /, but not on / typed in an input", async () => {
    go("tech");
    await ready();
    expect(screen.queryByRole("dialog")).toBeNull();
    const field = document.body.appendChild(document.createElement("input"));
    field.focus();
    fireEvent.keyDown(field, { key: "/" });
    expect(screen.queryByRole("dialog")).toBeNull();
    fireEvent.keyDown(field, { key: "k", metaKey: true }); // even inside an input
    expect(dialog()).toBeInTheDocument();
    expect(box()).toHaveFocus();
    fireEvent.keyDown(box(), { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    fireEvent.keyDown(document.body, { key: "/" });
    expect(dialog()).toBeInTheDocument();
    field.remove();
  });

  it("opens from the rail and the header, and Escape returns focus to the opener", async () => {
    go("tech");
    await ready();
    const goTo = screen.getByRole("button", { name: "Go to" });
    goTo.focus();
    fireEvent.click(goTo);
    expect(box()).toHaveFocus();
    fireEvent.keyDown(box(), { key: "Escape" });
    expect(goTo).toHaveFocus();
    fireEvent.click(screen.getByRole("button", { name: "Go to (Ctrl K)" }));
    expect(dialog()).toBeInTheDocument();
  });

  it("never offers a page the role cannot open", async () => {
    await open("tech");
    type("invoice");
    expect(options().join("|")).not.toMatch(/Invoices/);
    type("procurement");
    expect(options().join("|")).not.toMatch(/Inventory|Orders/);
    type("settings");
    expect(options().join("|")).not.toMatch(/Settings/);
  });

  it("offers read_only no quick actions", async () => {
    await open("read_only", ["tickets"]);
    await screen.findByRole("option", { name: /Tickets/ });
    expect(within(dialog()).queryByText("Actions")).toBeNull();
    type("zzz");
    expect(options()).toEqual(['Search tickets for "zzz"']);
    expect(within(dialog()).getByText("No matches")).toBeInTheDocument();
  });

  it("jumps to a ticket by number", async () => {
    await open("tech");
    type("123");
    const opt = await screen.findByRole("option", { name: /Go to ticket #123/ });
    await waitFor(() => expect(opt).not.toHaveAttribute("aria-disabled"));
    fireEvent.keyDown(box(), { key: "Enter" });
    expect(where()).toBe("/tickets/77");
  });

  it("says not found for a ticket that is missing or hidden", async () => {
    await open("tech");
    type("999");
    expect(await screen.findByRole("option", { name: /Ticket #999 not found/ })).toHaveAttribute("aria-disabled", "true");
    fireEvent.keyDown(box(), { key: "Enter" });
    expect(where()).toBe("/organizations");
    expect(dialog()).toBeInTheDocument();
  });

  it("moves with the arrow keys and opens with Enter", async () => {
    await open("tech");
    await screen.findByRole("option", { name: /Dispatch/ });
    fireEvent.keyDown(box(), { key: "ArrowDown" });
    const [first, second] = within(dialog()).getAllByRole("option");
    expect(box()).toHaveAttribute("aria-activedescendant", second.id);
    expect(first).toHaveAttribute("aria-selected", "false");
    fireEvent.keyDown(box(), { key: "Enter" });
    expect(where()).toBe("/dispatch");
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("lists Bookmarked, Recent and Actions when nothing is typed", async () => {
    await open("tech");
    await screen.findByRole("option", { name: /Dispatch/ });
    for (const g of ["Bookmarked", "Recent", "Actions"]) expect(within(dialog()).getByText(g)).toBeInTheDocument();
    expect(options().some((o) => o.startsWith("Organizations"))).toBe(true); // recent: the page we are on
    expect(options().filter((o) => o.startsWith("Tickets"))).toHaveLength(1); // bookmarked, so not repeated in Recent
    expect(box()).toHaveAttribute("aria-describedby", "cp-hints");
  });

  it("bookmarks the highlighted page with Alt+P and announces it", async () => {
    await open("tech");
    await screen.findByRole("option", { name: /Dispatch/ });
    fireEvent.keyDown(box(), { key: "ArrowDown" });
    fireEvent.keyDown(box(), { key: "p", code: "KeyP", altKey: true });
    await waitFor(() => expect(puts).toEqual([["tickets"]]));
    expect(within(dialog()).getByRole("status")).toHaveTextContent("Dispatch removed from bookmarks");
  });

  it("runs quick actions to the right page", async () => {
    await open("tech");
    type("new quote");
    fireEvent.keyDown(box(), { key: "Enter" });
    expect(where()).toBe("/quotes");
  });

  it("offers Record a payment to billing", async () => {
    await open("billing");
    fireEvent.click(await screen.findByRole("option", { name: /Record a payment/ }));
    expect(where()).toBe("/billing/payments");
  });

  it("finds settings tabs", async () => {
    await open("admin");
    type("holidays");
    fireEvent.click(within(dialog()).getByRole("option", { name: /Settings: Scheduling/ }));
    expect(where()).toBe("/admin/settings/scheduling");
  });
});
