import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";

const json = (body: unknown, status = 200) => () => new Response(JSON.stringify(body), { status });
const me = { contact_name: "Pat Payer", email: "pat@acme.com", organization_name: "Acme Corp", company_name: "Acme MSP", can_see_billing: false, can_see_all_tickets: false };
const day = 86400000;
const iso = (offsetMs: number) => new Date(Date.now() + offsetMs).toISOString();
const appt = (id: number, startOffset: number, over = {}) => ({ id, ticket_id: 40 + id, ticket_number: 10040 + id, ticket_subject: `Subject ${id}`, starts_at: iso(startOffset), ends_at: iso(startOffset + 3600000), tech_first_name: "Sam", ...over });

function go(handlers: Record<string, () => Response>) {
  vi.stubGlobal("fetch", vi.fn((url: string) => Promise.resolve(handlers[url]?.() ?? new Response("{}", { status: 404 }))));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><MemoryRouter initialEntries={["/portal/appointments"]}><App /></MemoryRouter></QueryClientProvider>);
}
afterEach(() => vi.unstubAllGlobals());

describe("portal appointments", () => {
  it("groups upcoming and past, shows the tech first name and links to the ticket", async () => {
    go({ "/api/portal/me": json(me), "/api/portal/appointments": json([appt(1, -5 * day), appt(2, 2 * day)]) });
    expect(await screen.findByText("Upcoming")).toBeInTheDocument();
    expect(screen.getByText("Past 30 days")).toBeInTheDocument();
    expect(screen.getAllByText(/· Sam/)).toHaveLength(2);
    expect(screen.getByRole("link", { name: /Subject 2/ })).toHaveAttribute("href", "/portal/tickets/42");
    expect(screen.getByRole("link", { name: /Subject 1/ })).toHaveAttribute("href", "/portal/tickets/41");
    expect(screen.getByRole("link", { name: "Appointments" })).toBeInTheDocument();
  });

  it("says so when there are no appointments", async () => {
    go({ "/api/portal/me": json(me), "/api/portal/appointments": json([]) });
    expect(await screen.findByText("No appointments scheduled")).toBeInTheDocument();
  });

  it("shows an error when the request fails", async () => {
    go({ "/api/portal/me": json(me), "/api/portal/appointments": json({ detail: "Boom" }, 500) });
    expect(await screen.findByText(/Boom/)).toBeInTheDocument();
    expect(screen.queryByText("No appointments scheduled")).toBeNull();
  });
});
