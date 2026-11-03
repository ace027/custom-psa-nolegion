import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import MailCalendarSettings from "./MailCalendarSettings";

function setup(patches: string[]) {
  vi.stubGlobal("fetch", vi.fn((raw: string, init?: RequestInit) => {
    const path = raw.split("?")[0];
    if (init?.method === "PATCH") patches.push(String(init.body));
    const body = path === "/api/v1/auth/me" ? { id: 1, email: "a@x.com", display_name: "A", role: "admin", permissions: ["config:manage"] }
      : path === "/api/v1/settings" ? { accounting_mailbox: "old@x.com", auto_ack_enabled: false, auto_ack_subject: "", auto_ack_body: "", escalation_email: null }
      : path === "/api/v1/mail/status" ? { configured: true, mailbox: "support@x.com", accounting_mailbox: null, last_send_error: "Access denied for accounting@x.com", last_send_error_at: "2026-01-02T10:00:00Z" }
      : {};
    return Promise.resolve(new Response(JSON.stringify(body)));
  }));
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MailCalendarSettings /></QueryClientProvider>);
}

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe("Mail and calendar settings", () => {
  it("shows the last send failure with a text label", async () => {
    setup([]);
    expect(await screen.findByText("Last send failure")).toBeTruthy();
    expect(screen.getByText(/Access denied for accounting@x.com/)).toBeTruthy();
  });

  it("saves the accounting address, and empty saves as null", async () => {
    const patches: string[] = [];
    setup(patches);
    const input = await screen.findByLabelText("Accounting sender address");
    fireEvent.change(input, { target: { value: "acct@x.com" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(patches).toContain(JSON.stringify({ accounting_mailbox: "acct@x.com" })));
    fireEvent.change(await screen.findByLabelText("Accounting sender address"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(patches).toContain(JSON.stringify({ accounting_mailbox: null })));
  });
});
