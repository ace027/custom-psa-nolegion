import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";

const json = (body: unknown, status = 200) => () => new Response(JSON.stringify(body), { status });
const PERMS = {
  tech: ["org:read", "user:read", "ticket:read", "billing:read", "quote:read", "quote:write"],
  admin: ["org:read", "user:read", "ticket:read", "billing:read", "quote:read", "quote:write", "quote:manage"],
  read_only: ["org:read", "user:read", "ticket:read", "billing:read", "quote:read"],
};
const me = (role: keyof typeof PERMS) => ({ id: 1, email: "u@example.com", display_name: "Una", role, permissions: PERMS[role] });
const quote = (over: object = {}) => ({
  id: 7, number: "Q-7", organization_id: 3, organization_name: "Newco", survey_id: 5, kind: "new", agreement_id: null, version: 1,
  status: "draft", is_expired: false,
  snapshot: {
    users: 10, devices: { priced: 9, out: 5, unknown: 0 },
    base_lines: [{ description: "Users", quantity: 10, unit_cents: 10000, amount_cents: 100000 }, { description: "Workstations", quantity: 8, unit_cents: 2000, amount_cents: 16000 }],
    factors: [
      { key: "hardware", label: "Hardware out of warranty", applies: true, bp: 2500, reason: "5 of 9 priced devices (56%) are out of warranty" },
      { key: "legacy_app", label: "Legacy line-of-business application", applies: false, bp: 0, reason: "None reported" },
    ],
  },
  base_cents: 126000, uplift_bp: 2500, computed_price_cents: 157500, final_price_cents: 157500, adjustment_reason: null, adjusted_by: null,
  term_months: 12, valid_until: null, effective_date: null, notes: null, decision_note: null, sent_to: null, resulting_agreement_id: null, ...over,
});
const survey = (over: object = {}) => ({
  id: 5, organization_id: 3, organization_name: "Newco", status: "in_progress", scheduled_for: null, tech_id: null, user_count: 10, site_count: 1, notes: null,
  completed_at: null, devices: [{ id: 1, device_class: "workstation", label: "PC1", make_model: null, serial: null, warranty_end: null, warranty_status: "out_of_warranty", priced: true, notes: null }], apps: [], ...over,
});

let calls: { url: string; init?: RequestInit }[] = [];
function go(path: string, role: keyof typeof PERMS, h: Record<string, () => Response>) {
  const handlers: Record<string, () => Response> = { "/api/auth/me": json(me(role)), ...h };
  vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => {
    calls.push({ url, init });
    return Promise.resolve(handlers[`${init?.method ?? "GET"} ${url}`]?.() ?? handlers[url]?.() ?? new Response("{}", { status: 404 }));
  }));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><MemoryRouter initialEntries={[path]}><App /></MemoryRouter></QueryClientProvider>);
}
beforeEach(() => { calls = []; localStorage.clear(); });
afterEach(() => vi.unstubAllGlobals());

describe("quotes", () => {
  it("shows the price with every number and reason behind it", async () => {
    go("/quotes/7", "tech", { "/api/quotes/7": json(quote()) });
    expect(await screen.findByTestId("price")).toHaveTextContent("$1,575.00");
    expect(screen.getByText(/5 of 9 priced devices \(56%\) are out of warranty/)).toBeInTheDocument();
    expect(screen.getByText("+25%")).toBeInTheDocument();
    expect(screen.getByText("no uplift")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Approve for sending" })).toBeInTheDocument();
  });

  it("an adjusted draft is submitted for approval and a tech cannot approve it", async () => {
    go("/quotes/7", "tech", { "/api/quotes/7": json(quote({ final_price_cents: 140000, adjustment_reason: "Referral" })) });
    expect(await screen.findByText(/Adjusted from the computed \$1,575.00: Referral/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Submit for approval" })).toBeInTheDocument();
  });

  it("only an admin sees Approve while waiting for approval", async () => {
    const h = { "/api/quotes/7": json(quote({ status: "needs_approval", final_price_cents: 140000, adjustment_reason: "x" })) };
    const { unmount } = go("/quotes/7", "tech", h);
    expect(await screen.findByText(/Waiting for an admin/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approve" })).toBeNull();
    unmount();
    go("/quotes/7", "admin", h);
    fireEvent.click(await screen.findByRole("button", { name: "Approve" }));
    await waitFor(() => expect(calls.some((c) => c.url === "/api/quotes/7/approve" && c.init?.method === "POST")).toBe(true));
  });

  it("read-only users see the quote but no actions", async () => {
    go("/quotes/7", "read_only", { "/api/quotes/7": json(quote({ status: "approved" })) });
    await screen.findByTestId("price");
    expect(screen.queryByRole("button", { name: /Mark as sent/ })).toBeNull();
    expect(screen.queryByRole("button", { name: "Submit for approval" })).toBeNull();
  });

  it("a sent quote can be accepted by an admin, with a start date", async () => {
    go("/quotes/7", "admin", { "/api/quotes/7": json(quote({ status: "sent" })), "POST /api/quotes/7/accept": json(quote({ status: "accepted", resulting_agreement_id: 9 })) });
    fireEvent.change(await screen.findByLabelText("Contract starts"), { target: { value: "2026-11-01" } });
    fireEvent.click(screen.getByRole("button", { name: "Client accepted" }));
    await waitFor(() => {
      const c = calls.find((x) => x.url === "/api/quotes/7/accept");
      expect(JSON.parse(String(c?.init?.body))).toEqual({ start_date: "2026-11-01" });
    });
  });
});

describe("survey form", () => {
  it("keeps unsaved answers on the device and restores them", async () => {
    localStorage.setItem("psa-survey-draft-5", JSON.stringify({ user_count: "42", site_count: "2", notes: "", devices: [], apps: [] }));
    go("/quotes/surveys/5", "tech", { "/api/surveys/5": json(survey()) });
    expect(await screen.findByText(/Restored unsaved changes/)).toBeInTheDocument();
    expect(screen.getByLabelText("Users")).toHaveValue("42");
  });

  it("saves the whole survey with a warranty-date device and clears the local draft", async () => {
    go("/quotes/surveys/5", "tech", { "/api/surveys/5": json(survey()), "PUT /api/surveys/5": json(survey({ user_count: 11 })) });
    fireEvent.change(await screen.findByLabelText("Users"), { target: { value: "11" } });
    expect(localStorage.getItem("psa-survey-draft-5")).not.toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "+ Server" }));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => {
      const c = calls.find((x) => x.init?.method === "PUT");
      const body = JSON.parse(String(c?.init?.body));
      expect(body.user_count).toBe(11);
      expect(body.devices.map((d: { device_class: string }) => d.device_class)).toEqual(["workstation", "server"]);
    });
    await waitFor(() => expect(localStorage.getItem("psa-survey-draft-5")).toBeNull());
  });

  it("a completed survey is read-only and offers to price it", async () => {
    go("/quotes/surveys/5", "tech", {
      "/api/surveys/5": json(survey({ status: "completed" })),
      "/api/quotes?organization_id=3": json([]),
      "/api/organizations/3": json({ id: 3, name: "Newco", status: "prospect" }),
      "/api/agreements?organization_id=3": json([]),
    });
    expect(await screen.findByRole("button", { name: "Create quote" })).toBeInTheDocument();
    expect(screen.getByLabelText("Users")).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Save" })).toBeNull();
  });
});

describe("rate card", () => {
  const settings = { per_user_rate_cents: 10000, workstation_rate_cents: 2000, server_rate_cents: 10000, network_rate_cents: 0, other_rate_cents: 0, hardware_uplift_bp: 2500, server_uplift_bp: 0, legacy_app_uplift_bp: 1500, term_months: 12, valid_days: 30, agreement_taxable: false, intro_text: null };
  it("shows percentages and is read-only for non-admins", async () => {
    go("/quotes/rates", "tech", { "/api/quotes/settings": json(settings) });
    expect(await screen.findByLabelText("Hardware uplift")).toHaveValue("25");
    expect(screen.getByLabelText("Legacy application uplift")).toHaveValue("15");
    expect(screen.getByLabelText("Hardware uplift")).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Save rate card" })).toBeNull();
  });
  it("an admin saves dollars and percentages as cents and basis points", async () => {
    go("/quotes/rates", "admin", { "/api/quotes/settings": json(settings), "PATCH /api/quotes/settings": json(settings) });
    fireEvent.change(await screen.findByLabelText("Hardware uplift"), { target: { value: "30" } });
    fireEvent.click(screen.getByRole("button", { name: "Save rate card" }));
    await waitFor(() => {
      const c = calls.find((x) => x.init?.method === "PATCH");
      const body = JSON.parse(String(c?.init?.body));
      expect(body.hardware_uplift_bp).toBe(3000);
      expect(body.per_user_rate_cents).toBe(10000);
    });
  });
});
