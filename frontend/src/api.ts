export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export async function api<T>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const { json, headers, ...rest } = init;
  const res = await fetch(`/api${path}`, {
    credentials: "same-origin",
    ...rest,
    headers: {
      // Required by the API on every state-changing request (CSRF defense in depth).
      "X-Requested-With": "psa",
      ...(json !== undefined ? { "Content-Type": "application/json" } : {}),
      ...headers,
    },
    body: json !== undefined ? JSON.stringify(json) : rest.body,
  });
  if (!res.ok) {
    let message = res.statusText;
    try {
      const body = await res.json();
      message = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, message);
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

export type Role = "admin" | "tech" | "billing" | "read_only";
export const ROLES: Role[] = ["admin", "tech", "billing", "read_only"];

export interface Me {
  id: number;
  email: string;
  display_name: string;
  role: Role;
  permissions: string[];
}
export interface User extends Omit<Me, "permissions"> {
  is_active: boolean;
  last_login_at: string | null;
}
export interface Organization {
  id: number;
  name: string;
  status: "active" | "inactive";
  billing_address: string | null;
  notes: string | null;
  archived_at: string | null;
}
export interface Site {
  id: number;
  organization_id: number;
  name: string;
  address_line1: string | null;
  city: string | null;
  state: string | null;
  postal_code: string | null;
  archived_at: string | null;
}
export interface Contact {
  id: number;
  organization_id: number;
  site_id: number | null;
  name: string;
  email: string | null;
  phone: string | null;
  title: string | null;
  is_primary: boolean;
  is_billing_contact: boolean;
  archived_at: string | null;
}
export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}
export interface AuditEntry {
  id: number;
  occurred_at: string;
  actor_type: string;
  actor_id: number | null;
  action: string;
  entity_type: string | null;
  entity_id: number | null;
  organization_id: number | null;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  detail: Record<string, unknown> | null;
}
