import { describe, expect, it } from "vitest";
import { money, parseMoney, parsePercent, percent, qty } from "./money";

describe("money()", () => {
  it.each([
    [0, "$0.00"], [5, "$0.05"], [100, "$1.00"], [123456, "$1,234.56"], [-2500, "-$25.00"],
    [100000000, "$1,000,000.00"], [99, "$0.99"],
  ])("%i -> %s", (cents, text) => expect(money(cents)).toBe(text));
});

describe("parseMoney(): exact integer cents, no floating point", () => {
  it.each([
    ["12.34", 1234], ["12", 1200], ["12.5", 1250], ["$1,234.56", 123456], ["0.07", 7], [".5", 50],
    ["-10.00", -1000], ["  19.99  ", 1999], ["1,000", 100000], ["0.29", 29], ["1.10", 110],
  ])("%s -> %i", (text, cents) => expect(parseMoney(text)).toBe(cents));

  it.each(["", "abc", "12.345", "1.2.3", "$", "-", "12 dollars", "1e3"])("rejects %j", (text) =>
    expect(parseMoney(text)).toBeNull(),
  );

  it("round-trips with money() for every cent value in a range (no float drift)", () => {
    for (let c = -5000; c <= 5000; c++) expect(parseMoney(money(c))).toBe(c);
    for (const c of [1, 10, 29, 57, 58, 113, 1005, 1099, 999999]) expect(parseMoney(money(c))).toBe(c);
  });
});

describe("percent", () => {
  it("formats basis points", () => {
    expect(percent(825)).toBe("8.25%");
    expect(percent(1000)).toBe("10%");
    expect(percent(0)).toBe("0%");
    expect(percent(50)).toBe("0.5%");
  });
  it("parses to basis points", () => {
    expect(parsePercent("8.25")).toBe(825);
    expect(parsePercent("10")).toBe(1000);
    expect(parsePercent("8.5%")).toBe(850);
    expect(parsePercent("0")).toBe(0);
    expect(parsePercent("abc")).toBeNull();
    expect(parsePercent("8.255")).toBeNull();
  });
  it("trims quantities", () => {
    expect(qty("25.0000")).toBe("25");
    expect(qty("0.7500")).toBe("0.75");
    expect(qty("0.0000")).toBe("0");
  });
});
