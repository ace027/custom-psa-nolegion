import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "./api";

const mockFetch = (status: number, body: unknown) =>
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(new Response(status === 204 ? null : JSON.stringify(body), { status })),
  );

afterEach(() => vi.unstubAllGlobals());

describe("api()", () => {
  it("sends the CSRF header and JSON body", async () => {
    mockFetch(200, { ok: true });
    await api("/organizations", { method: "POST", json: { name: "x" } });
    const [url, init] = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toBe("/api/organizations");
    expect(init.headers["X-Requested-With"]).toBe("psa");
    expect(init.headers["Content-Type"]).toBe("application/json");
    expect(init.body).toBe('{"name":"x"}');
  });

  it("returns undefined for 204", async () => {
    mockFetch(204, null);
    await expect(api("/auth/logout", { method: "POST" })).resolves.toBeUndefined();
  });

  it("throws ApiError with the server's detail message", async () => {
    mockFetch(409, { detail: "An active organization with that name already exists" });
    const err = (await api("/organizations").catch((e) => e)) as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(409);
    expect(err.message).toContain("already exists");
  });
});
