import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import App from "./App";

const me = { id: 1, email: "tech@example.com", display_name: "Tess Tech", role: "tech", permissions: ["org:read", "ticket:read"], notify_assigned: true, notify_sla: true, notify_reply: false };

it("lets a user turn their own notification emails on and off", async () => {
  const calls: string[] = [];
  vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => {
    calls.push(`${init?.method ?? "GET"} ${url} ${init?.body ?? ""}`);
    return Promise.resolve(new Response(JSON.stringify(url === "/api/auth/me" || url.endsWith("notifications") ? me : {}), { status: 200 }));
  }));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={qc}><MemoryRouter initialEntries={["/profile"]}><App /></MemoryRouter></QueryClientProvider>);
  const box = await screen.findByLabelText(/A customer replies on my ticket/);
  expect(box).not.toBeChecked();
  fireEvent.click(box);
  await waitFor(() => expect(calls.some((c) => c.startsWith("PATCH /api/auth/me/notifications") && c.includes('"notify_reply":true'))).toBe(true));
  vi.unstubAllGlobals();
});
