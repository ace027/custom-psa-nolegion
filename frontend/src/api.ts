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

// ---- Phase 2 ----
export type TicketStatus = "new" | "open" | "waiting_on_customer" | "resolved" | "closed";
export const STATUSES: TicketStatus[] = ["new", "open", "waiting_on_customer", "resolved", "closed"];
export const STATUS_LABEL: Record<TicketStatus, string> = {
  new: "New",
  open: "Open",
  waiting_on_customer: "Waiting on customer",
  resolved: "Resolved",
  closed: "Closed",
};
export type SlaState = "none" | "ok" | "at_risk" | "breached" | "paused" | "done";

export interface Ticket {
  id: number;
  number: number;
  organization_id: number | null;
  organization_name: string | null;
  contact_id: number | null;
  contact_name: string | null;
  site_id: number | null;
  queue_id: number;
  queue_name: string;
  category_id: number | null;
  category_name: string | null;
  priority_id: number;
  priority_name: string;
  priority_rank: number;
  status: TicketStatus;
  assignee_id: number | null;
  assignee_name: string | null;
  subject: string;
  description: string | null;
  source: string;
  requester_email: string | null;
  needs_triage: boolean;
  sla_state: SlaState;
  sla_first_response_due: string | null;
  sla_resolution_due: string | null;
  first_responded_at: string | null;
  created_at: string;
  updated_at: string;
}
export interface Note {
  id: number;
  author_name: string | null;
  author_email: string | null;
  visibility: "internal" | "customer";
  source: string;
  body: string;
  created_at: string;
  email_status: string | null;
}
export interface TimeEntry {
  id: number;
  user_id: number;
  work_type_id: number;
  work_date: string;
  minutes_actual: number;
  minutes_billable: number;
  billable: boolean;
  note: string | null;
  voided_at: string | null;
}
export interface Attachment {
  id: number;
  filename: string;
  size_bytes: number;
}
export interface Lookup {
  id: number;
  name: string;
  archived_at: string | null;
}
export interface Queue extends Lookup {
  is_default: boolean;
}
export interface Priority extends Lookup {
  rank: number;
  first_response_minutes: number | null;
  resolution_minutes: number | null;
  is_default: boolean;
}
export interface AppSettings {
  timezone: string;
  business_days: number[];
  business_start_minute: number;
  business_end_minute: number;
  billing_increment_minutes: number;
  sla_at_risk_percent: number;
}
export interface Dashboard {
  my_open: Ticket[];
  unassigned: Ticket[];
  sla_at_risk: Ticket[];
  counts: Record<string, number>;
}
export interface MailStatus {
  configured: boolean;
  mailbox: string | null;
  worker_seen_at: string | null;
  last_poll_at: string | null;
  last_success_at: string | null;
  last_error: string | null;
  last_error_at: string | null;
  messages_ingested: number;
  outbound_pending: number;
  outbound_failed: number;
  tickets_needing_triage: number;
}
