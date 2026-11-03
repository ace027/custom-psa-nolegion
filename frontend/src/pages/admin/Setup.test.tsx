import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../../App";
import { visibleItems } from "../../nav/navConfig";

const json = (body: unknown, status = 200) => () => new Response(JSON.stringify(body), { status });
const me = (role: string) => ({ id: 1, email: "u@example.com", display_name: "Una", role, permissions: role === "admin" ? ["config:manage", "user:manage"] : ["config:manage"] });
const STATUS = {
  steps: [
    { step: "staff_sso", status: "ok", message: "Staff sign-in works" },
    { step: "portal_sso", status: "missing", message: "Portal app not set up" },
    { step: "mail", status: "restart_needed", message: "Restart to use mail" },
    { step: "calendar", status: "error", message: "Calendar failed" },
  ],
};

let calls: string[] = [];
function go(h: Record<string, () => Response>, role = "admin", path = "/setup") {
  const handlers: Record<string, () => Response> = { "/api/v1/auth/me": json(me(role)), ...h };
  vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => {
    const k = init?.method && init.method !== "GET" ? `${init.method} ${url}` : url;
    calls.push(k);
    return Promise.resolve(handlers[k]?.() ?? new Response("{}", { status: 404 }));
  }));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><MemoryRouter initialEntries={[path]}><App /></MemoryRouter></QueryClientProvider>);
}
beforeEach(() => { calls = []; });
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

describe("setup wizard", () => {
  it("renders steps with text status labels", async () => {
    go({ "/api/v1/onboarding/status": json(STATUS) });
    await screen.findAllByText("Staff sign-in works");
    for (const t of ["Done", "Needs action", "Restart needed", "Error"]) expect((await screen.findAllByText(t)).length).toBeGreaterThan(0);
    expect(screen.getByText("Secrets are stored in Azure Key Vault and are never shown.")).toBeInTheDocument();
  });

  it("says setup is off when status is 404", async () => {
    go({});
    expect(await screen.findByText("Setup is not enabled on this install.")).toBeInTheDocument();
  });

  it("shows a retry message after a consent error", async () => {
    go({ "/api/v1/onboarding/status": json(STATUS) }, "admin", "/setup?consent=error");
    expect(await screen.findByText(/did not complete/)).toBeInTheDocument();
  });

  it("creates the portal app", async () => {
    go({
      "/api/v1/onboarding/status": json(STATUS),
      "POST /api/v1/onboarding/portal-app": json({ app_id: "a", created: true }),
    });
    await screen.findAllByText("Staff sign-in works");
    fireEvent.click(screen.getAllByRole("button", { name: "Create" })[0]);
    await waitFor(() => expect(calls).toContain("POST /api/v1/onboarding/portal-app"));
  });

  it("shows the PowerShell after creating the mail app", async () => {
    go({
      "/api/v1/onboarding/status": json(STATUS),
      "POST /api/v1/onboarding/mail-app": json({ app_id: "a", service_principal_object_id: "s", created: true, powershell: "New-ApplicationAccessPolicy -X" }),
    });
    await screen.findAllByText("Staff sign-in works");
    fireEvent.change(screen.getByLabelText("Shared mailbox address"), { target: { value: "help@example.com" } });
    fireEvent.click(screen.getAllByRole("button", { name: "Create" })[1]);
    expect(await screen.findByText("New-ApplicationAccessPolicy -X")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Copy" })).toBeInTheDocument();
  });

  it("asks before finishing", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    go({ "/api/v1/onboarding/status": json(STATUS), "POST /api/v1/onboarding/finish": json({ removed_scopes: [] }) });
    await screen.findAllByText("Staff sign-in works");
    fireEvent.click(screen.getByRole("button", { name: "Finish" }));
    expect(confirm).toHaveBeenCalledWith("This removes the setup permission from your account. You can grant it again later.");
    expect(calls).not.toContain("POST /api/v1/onboarding/finish");
  });

  it("keeps non-admins out", async () => {
    go({ "/api/v1/onboarding/status": json(STATUS) }, "manager");
    await waitFor(() => expect(screen.queryByText("Setup")).toBeNull());
    expect(calls).not.toContain("/api/v1/onboarding/status");
  });

  it("lists Setup in the nav for admins only", () => {
    const ids = (role: string) => visibleItems(me(role) as never).map((i) => i.id);
    expect(ids("admin")).toContain("setup");
    expect(ids("manager")).not.toContain("setup");
  });
});
