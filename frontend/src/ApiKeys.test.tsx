import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";

const json = (body: unknown, status = 200) => () => new Response(JSON.stringify(body), { status });
const ADMIN = ["org:read", "ticket:read", "ticket:write", "user:manage", "apikey:manage", "portal:manage"];
const me = (role: string, permissions: string[]) => ({ id: 1, email: "u@example.com", display_name: "Una", role, permissions });
const key = (over = {}) => ({
  id: 4, name: "n8n", prefix: "ab12cd34", permissions: ["ticket:read"], owner_id: 1, owner_name: "Una",
  expires_at: "2027-01-01T00:00:00Z", revoked_at: null, last_used_at: null, created_at: "2026-10-01T00:00:00Z", state: "active", ...over,
});

let calls: string[] = [];
function go(path: string, role: string, perms: string[], h: Record<string, () => Response>) {
  const handlers: Record<string, () => Response> = { "/api/auth/me": json(me(role, perms)), ...h };
  vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => {
    const k = init?.method && init.method !== "GET" ? `${init.method} ${url}` : url;
    calls.push(`${k} ${init?.body ?? ""}`);
    return Promise.resolve(handlers[k]?.() ?? new Response("{}", { status: 404 }));
  }));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><MemoryRouter initialEntries={[path]}><App /></MemoryRouter></QueryClientProvider>);
}
beforeEach(() => { calls = []; });
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

describe("api keys", () => {
  it("lists keys without any secret", async () => {
    go("/api-keys", "admin", ADMIN, { "/api/api-keys": json([key(), key({ id: 5, name: "old", state: "revoked" })]) });
    expect(await screen.findByText("n8n")).toBeInTheDocument();
    expect(screen.getAllByText("psa_ab12cd34_…").length).toBe(2);
    expect(screen.getAllByRole("button", { name: /^Revoke / }).length).toBe(1);
  });

  it("offers no forbidden permissions", async () => {
    go("/api-keys", "admin", ADMIN, { "/api/api-keys": json([]) });
    await screen.findByText("Create a key");
    expect(await screen.findByLabelText("ticket:write")).toBeInTheDocument();
    for (const p of ["user:manage", "apikey:manage", "portal:manage"]) expect(screen.queryByLabelText(p)).toBeNull();
  });

  it("shows the token once after create", async () => {
    go("/api-keys", "admin", ADMIN, {
      "/api/api-keys": json([]),
      "POST /api/api-keys": json({ key: key(), token: "psa_ab12cd34_SECRETSECRETSECRETSECRET" }, 201),
    });
    fireEvent.change(await screen.findByLabelText("Name"), { target: { value: "n8n" } });
    fireEvent.click(await screen.findByLabelText("ticket:read"));
    fireEvent.click(screen.getByRole("button", { name: "Create key" }));
    expect(await screen.findByDisplayValue("psa_ab12cd34_SECRETSECRETSECRETSECRET")).toHaveAttribute("readonly");
    expect(screen.getByText("Copy this key now. It will not be shown again.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Copy" })).toBeInTheDocument();
    await waitFor(() => expect(calls.some((c) => c.startsWith("POST /api/api-keys ") && c.includes('"expires_in_days":365') && c.includes('"ticket:read"'))).toBe(true));
    fireEvent.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(screen.queryByDisplayValue(/SECRET/)).toBeNull();
  });

  it("revokes only after confirmation", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValueOnce(false).mockReturnValueOnce(true);
    go("/api-keys", "admin", ADMIN, { "/api/api-keys": json([key()]), "POST /api/api-keys/4/revoke": json(key({ state: "revoked" })) });
    const btn = await screen.findByRole("button", { name: "Revoke n8n" });
    fireEvent.click(btn);
    expect(calls.some((c) => c.startsWith("POST /api/api-keys/4/revoke"))).toBe(false);
    fireEvent.click(btn);
    await waitFor(() => expect(calls.some((c) => c.startsWith("POST /api/api-keys/4/revoke"))).toBe(true));
    expect(confirm).toHaveBeenCalledTimes(2);
  });

  it("is hidden without the permission", async () => {
    go("/api-keys", "tech", ["org:read", "ticket:read"], { "/api/tickets": json([]) });
    await waitFor(() => expect(screen.queryByText("Create a key")).toBeNull());
    expect(screen.queryByRole("link", { name: "API keys" })).toBeNull();
  });
});
