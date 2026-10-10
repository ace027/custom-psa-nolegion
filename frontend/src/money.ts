/** Money is integer cents everywhere. Parsing avoids floating point: "12.34" -> 1234. */
export function money(cents: number): string {
  const sign = cents < 0 ? "-" : "";
  const abs = Math.abs(cents);
  const dollars = Math.trunc(abs / 100).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return `${sign}$${dollars}.${String(abs % 100).padStart(2, "0")}`;
}

/** "1,234.5" -> 123450; returns null for anything that is not a plain amount. */
export function parseMoney(text: string): number | null {
  const m = /^(-?)\s*\$?\s*(\d[\d,]*)?(?:\.(\d{0,2}))?$/.exec(text.trim());
  if (!m || (m[2] === undefined && m[3] === undefined)) return null;
  const dollars = Number((m[2] ?? "0").replace(/,/g, ""));
  const cents = Number((m[3] ?? "").padEnd(2, "0"));
  const total = dollars * 100 + cents;
  return Number.isSafeInteger(total) ? (m[1] ? -total : total) : null;
}

/** basis points -> "8.25%" */
export const percent = (bp: number) => `${(bp / 100).toFixed(2).replace(/\.?0+$/, "")}%`;

/** "8.25" -> 825 */
export function parsePercent(text: string): number | null {
  const m = /^(\d{1,3})(?:\.(\d{0,2}))?$/.exec(text.trim().replace(/%$/, ""));
  if (!m) return null;
  return Number(m[1]) * 100 + Number((m[2] ?? "").padEnd(2, "0"));
}

export const qty = (q: string) => q.replace(/\.?0+$/, "") || "0";
