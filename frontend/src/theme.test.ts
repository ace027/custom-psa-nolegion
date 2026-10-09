import { afterEach, describe, expect, it, vi } from "vitest";
import { applyTheme, storedChoice } from "./theme";

const mq = (dark: boolean) => vi.fn(() => ({ matches: dark, addEventListener() {}, removeEventListener() {} }));

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
  document.documentElement.classList.remove("dark");
});

describe("theme", () => {
  it("defaults to following the system and only remembers an explicit choice", () => {
    expect(storedChoice()).toBe("system");
    localStorage.setItem("psa-theme", "dark");
    expect(storedChoice()).toBe("dark");
    localStorage.setItem("psa-theme", "garbage");
    expect(storedChoice()).toBe("system");
  });

  it("applies dark for an explicit dark choice and for system dark, light otherwise", () => {
    vi.stubGlobal("matchMedia", mq(true));
    applyTheme("light");
    expect(document.documentElement.classList.contains("dark")).toBe(false);
    applyTheme("dark");
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    applyTheme("light");
    applyTheme("system");
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    vi.stubGlobal("matchMedia", mq(false));
    applyTheme("system");
    expect(document.documentElement.classList.contains("dark")).toBe(false);
  });

  it("falls back to light when the browser has no matchMedia or blocks storage", () => {
    vi.stubGlobal("matchMedia", undefined);
    applyTheme("system");
    expect(document.documentElement.classList.contains("dark")).toBe(false);
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("blocked"); });
    expect(storedChoice()).toBe("system");
    vi.restoreAllMocks();
  });
});
