import { formatInZone, fromBoardDate, toBoardDate, zoneDayRange, zoneWeekRange } from "./zone";

const CHI = "America/Chicago";
const hours = (r: { from: string; to: string }) => (Date.parse(r.to) - Date.parse(r.from)) / 3_600_000;
const wall = (d: Date) => [d.getFullYear(), d.getMonth() + 1, d.getDate(), d.getHours(), d.getMinutes()];

describe("toBoardDate / fromBoardDate", () => {
  it("shows the zone's wall clock", () => {
    expect(wall(toBoardDate("2030-01-07T14:00:00Z", CHI))).toEqual([2030, 1, 7, 8, 0]);
    expect(wall(toBoardDate("2030-07-01T14:00:00Z", CHI))).toEqual([2030, 7, 1, 9, 0]);
  });

  it("round-trips across spring-forward (2030-03-10)", () => {
    for (const iso of [
      "2030-03-10T05:59:00.000Z", // 23:59 the day before
      "2030-03-10T07:59:00.000Z", // 01:59 CST, last minute before the jump
      "2030-03-10T08:00:00.000Z", // 03:00 CDT
      "2030-03-10T12:30:00.000Z",
    ]) {
      expect(fromBoardDate(toBoardDate(iso, CHI), CHI)).toBe(iso);
    }
    expect(wall(toBoardDate("2030-03-10T07:59:00Z", CHI))).toEqual([2030, 3, 10, 1, 59]);
    expect(wall(toBoardDate("2030-03-10T08:00:00Z", CHI))).toEqual([2030, 3, 10, 3, 0]);
  });

  it("round-trips across fall-back (2030-11-03), the repeated hour maps to its first occurrence", () => {
    for (const iso of ["2030-11-03T05:00:00.000Z", "2030-11-03T05:59:00.000Z", "2030-11-03T08:00:00.000Z", "2030-11-03T18:00:00.000Z"]) {
      expect(fromBoardDate(toBoardDate(iso, CHI), CHI)).toBe(iso);
    }
    expect(wall(toBoardDate("2030-11-03T06:30:00Z", CHI))).toEqual([2030, 11, 3, 1, 30]); // CDT
    expect(wall(toBoardDate("2030-11-03T07:30:00Z", CHI))).toEqual([2030, 11, 3, 1, 30]); // CST
    expect(fromBoardDate(toBoardDate("2030-11-03T07:30:00Z", CHI), CHI)).toBe("2030-11-03T06:30:00.000Z");
  });

  it("converts a Sydney-local instant for a Chicago board", () => {
    // 2030-01-08 09:00 in Sydney (UTC+11) is 2030-01-07 16:00 in Chicago
    const iso = new Date("2030-01-07T22:00:00Z").toISOString();
    expect(wall(toBoardDate("2030-01-08T09:00:00+11:00", CHI))).toEqual([2030, 1, 7, 16, 0]);
    expect(wall(toBoardDate(iso, "Australia/Sydney"))).toEqual([2030, 1, 8, 9, 0]);
    expect(fromBoardDate(toBoardDate("2030-01-08T09:00:00+11:00", CHI), CHI)).toBe(iso);
  });
});

describe("zoneDayRange / zoneWeekRange", () => {
  it("is 24h on an ordinary day", () => {
    expect(zoneDayRange("2030-01-07", CHI)).toEqual({ from: "2030-01-07T06:00:00.000Z", to: "2030-01-08T06:00:00.000Z" });
  });
  it("is 23h on the spring-forward day", () => {
    const r = zoneDayRange("2030-03-10", CHI);
    expect(r).toEqual({ from: "2030-03-10T06:00:00.000Z", to: "2030-03-11T05:00:00.000Z" });
    expect(hours(r)).toBe(23);
  });
  it("is 25h on the fall-back day", () => {
    const r = zoneDayRange("2030-11-03", CHI);
    expect(r).toEqual({ from: "2030-11-03T05:00:00.000Z", to: "2030-11-04T06:00:00.000Z" });
    expect(hours(r)).toBe(25);
  });
  it("handles month and year ends", () => {
    expect(zoneDayRange("2030-12-31", CHI).to).toBe("2031-01-01T06:00:00.000Z");
  });
  it("rejects a bad day", () => {
    expect(() => zoneDayRange("soon", CHI)).toThrow();
  });
  it("week runs Monday to Monday for any day in it", () => {
    const wk = { from: "2030-01-07T06:00:00.000Z", to: "2030-01-14T06:00:00.000Z" };
    for (const d of ["2030-01-07", "2030-01-10", "2030-01-13"]) expect(zoneWeekRange(d, CHI)).toEqual(wk);
  });
  it("week holding spring-forward is 167h, fall-back is 169h", () => {
    const spring = zoneWeekRange("2030-03-10", CHI); // a Sunday: belongs to the week starting 03-04
    expect(spring).toEqual({ from: "2030-03-04T06:00:00.000Z", to: "2030-03-11T05:00:00.000Z" });
    expect(hours(spring)).toBe(167);
    expect(hours(zoneWeekRange("2030-11-03", CHI))).toBe(169);
  });
});

describe("formatInZone", () => {
  it("formats in the zone, not the browser", () => {
    expect(formatInZone("2030-01-07T14:30:00Z", CHI, "HH:mm")).toBe("08:30");
    expect(formatInZone("2030-01-07T14:30:00Z", "Australia/Sydney", "HH:mm")).toBe("01:30");
    expect(formatInZone("2030-01-07T14:30:00Z", CHI, "EEE HH:mm")).toBe("Mon 08:30");
  });
});
