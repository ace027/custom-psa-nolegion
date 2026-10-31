// White-label branding. Everything here comes from VITE_BRAND_* build variables.
export interface Brand {
  name: string;
  mark: string;
  logoUrl: string | null;
  colors: Partial<Record<string, string>>;
}

function parseColors(raw: string | undefined): Partial<Record<string, string>> {
  if (!raw) return {};
  try {
    const v: unknown = JSON.parse(raw);
    if (v && typeof v === "object" && !Array.isArray(v)) {
      const out: Record<string, string> = {};
      for (const [k, val] of Object.entries(v)) if (typeof val === "string") out[k] = val;
      return out;
    }
    console.warn("VITE_BRAND_COLORS must be a JSON object; ignored");
  } catch {
    console.warn("VITE_BRAND_COLORS is not valid JSON; ignored");
  }
  return {};
}

const env = import.meta.env;
const name = (env.VITE_BRAND_NAME ?? "").trim() || "PSA";

export const BRAND: Brand = {
  name,
  mark: (env.VITE_BRAND_MARK ?? "").trim() || name.charAt(0).toUpperCase(),
  logoUrl: (env.VITE_BRAND_LOGO_URL ?? "").trim() || null,
  colors: parseColors(env.VITE_BRAND_COLORS),
};

/** Set the document title and any colour overrides (keys are @theme token names, e.g. "blue-600"). */
export function applyBrand(doc: Document = document, brand: Brand = BRAND): void {
  doc.title = brand.name;
  for (const [token, value] of Object.entries(brand.colors)) {
    if (value) doc.documentElement.style.setProperty(`--color-${token.replace(/^--color-/, "")}`, value);
  }
}
