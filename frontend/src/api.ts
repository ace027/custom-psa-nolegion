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
  company_name: string | null;
  company_address: string | null;
  invoice_footer: string | null;
  timezone: string;
  business_days: number[];
  business_start_minute: number;
  business_end_minute: number;
  billing_increment_minutes: number;
  sla_at_risk_percent: number;
  statement_subject: string;
  statement_body: string;
  auto_prepare_reminders: boolean;
  auto_prepare_statements: boolean;
  reminder_min_gap_days: number;
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

// ---- Phase 3: contracts and invoicing (money = integer cents) ----
export type InvoiceStatus = "draft" | "final" | "void";
export type RunStatus = "draft" | "reviewed" | "finalized" | "cancelled";
export interface Invoice {
  id: number;
  number: string | null;
  organization_id: number;
  organization_name: string;
  status: InvoiceStatus;
  billing_run_id: number | null;
  period_start: string | null;
  period_end: string | null;
  invoice_date: string | null;
  due_date: string | null;
  terms_days: number | null;
  subtotal_cents: number;
  tax_cents: number;
  total_cents: number;
  memo: string | null;
  warnings: string[];
  void_reason: string | null;
  created_at: string;
  paid_cents: number | null;
  written_off_cents: number | null;
  balance_cents: number | null;
  payment_status: "unpaid" | "partial" | "paid" | "written_off" | null;
  is_overdue: boolean;
  days_past_due: number;
}
export interface InvoiceLine {
  id: number;
  kind: "time" | "product" | "agreement" | "manual";
  description: string;
  quantity: string;
  unit_price_cents: number;
  amount_cents: number;
  tax_rate_bp: number;
  tax_cents: number;
}
export interface InvoiceDetail extends Invoice {
  lines: InvoiceLine[];
  payments: {
    application_id: number;
    payment_id: number;
    amount_cents: number;
    received_on: string;
    method: string;
    reference: string | null;
    voided_at: string | null;
    void_reason: string | null;
  }[];
  write_offs: { id: number; amount_cents: number; reason: string; created_at: string; voided_at: string | null; void_reason: string | null }[];
}
export interface Run {
  id: number;
  period_start: string;
  period_end: string;
  status: RunStatus;
  created_at: string;
  reviewed_at: string | null;
  finalized_at: string | null;
  invoice_count: number;
  total_cents: number;
  warnings: string[];
}
export interface RunDetail extends Run {
  invoices: Invoice[];
}
export interface Agreement {
  id: number;
  organization_id: number;
  organization_name: string;
  name: string;
  type: "per_user" | "per_device" | "flat";
  unit_price_cents: number;
  quantity: number;
  taxable: boolean;
  start_date: string;
  end_date: string | null;
  notes: string | null;
  monthly_amount_cents: number;
}
export interface Product {
  id: number;
  sku: string | null;
  name: string;
  description: string | null;
  unit_price_cents: number;
  cost_cents: number | null;
  taxable: boolean;
  archived_at: string | null;
}
export interface Charge {
  id: number;
  organization_id: number;
  ticket_id: number | null;
  description: string;
  quantity: string;
  unit_price_cents: number;
  taxable: boolean;
  charged_on: string;
  invoice_line_id: number | null;
  voided_at: string | null;
}
export interface WorkTypeBilling {
  id: number;
  name: string;
  rate_cents: number | null;
  taxable: boolean;
  archived_at: string | null;
}
export interface OrgBilling {
  payment_terms_days: number;
  tax_rate_bp: number;
  do_not_remind: boolean;
  rates: { work_type_id: number; rate_cents: number }[];
}

// ---- payments ----
export type PaymentMethod = "check" | "ach" | "card" | "cash" | "other";
export const METHODS: PaymentMethod[] = ["check", "ach", "card", "cash", "other"];
export interface Payment {
  id: number;
  organization_id: number;
  organization_name: string;
  amount_cents: number;
  received_on: string;
  method: PaymentMethod;
  reference: string | null;
  notes: string | null;
  status: "active" | "void";
  applied_cents: number;
  unapplied_cents: number;
  void_reason: string | null;
  created_at: string;
}
export interface PaymentDetail extends Payment {
  applications: { id: number; invoice_id: number; amount_cents: number; voided_at: string | null; void_reason: string | null }[];
}
export interface AgingRow {
  organization_id: number;
  organization_name: string;
  current_cents: number;
  d1_30_cents: number;
  d31_60_cents: number;
  d61_90_cents: number;
  d90_plus_cents: number;
  total_open_cents: number;
  credit_cents: number;
  open_invoice_count: number;
  overdue_invoice_count: number;
  oldest_days_past_due: number;
}
export interface Receivables {
  as_of: string;
  rows: AgingRow[];
  totals: AgingRow;
}

// ---- statements and reminders ----
export interface ReminderStage {
  id: number;
  position: number;
  name: string;
  days_past_due: number;
  subject: string;
  body: string;
  enabled: boolean;
}
export interface NoticeInvoice {
  invoice_id: number;
  number: string | null;
  due_date: string | null;
  balance_cents: number;
  days_past_due: number;
  new_stage: boolean;
}
export type NoticeStatus = "pending" | "sent" | "dismissed" | "expired";
export interface Notice {
  id: number;
  kind: "reminder" | "statement";
  organization_id: number;
  organization_name: string;
  status: NoticeStatus;
  manual: boolean;
  stage_name: string | null;
  subject: string;
  body_text: string;
  to_emails: string[];
  blocked_reason: string | null;
  statement_id: number | null;
  stale: boolean;
  total_due_cents: number;
  created_at: string;
  decided_at: string | null;
  dismiss_reason: string | null;
  email_status: string | null;
  invoices: NoticeInvoice[];
}
export interface SendResult {
  id: number;
  ok: boolean;
  error: string | null;
}
export interface Statement {
  id: number;
  organization_id: number;
  as_of: string;
  created_at: string;
  total_due_cents: number;
  overdue_cents: number;
  credit_cents: number;
  invoice_count: number;
}
