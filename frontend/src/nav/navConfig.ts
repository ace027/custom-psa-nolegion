import type { Me, Role } from "../api";
import { can } from "../auth";

/** The one list of staff pages. The rail, All pages, the Admin sub-nav, the header bookmark star,
 *  the command palette (16-04) and the navigation tests all read it. Ids are saved in users'
 *  bookmarks on the server, so never rename an id; retire it instead (unknown ids are hidden). */

export type SectionId = "service" | "scheduling" | "clients" | "finance" | "reports" | "admin";

export interface NavSection {
  id: SectionId;
  label: string;
}

export const NAV_SECTIONS: NavSection[] = [
  { id: "service", label: "Service desk" },
  { id: "scheduling", label: "Scheduling" },
  { id: "clients", label: "Clients & sales" },
  { id: "finance", label: "Finance" },
  { id: "reports", label: "Reports" },
  { id: "admin", label: "Admin" },
];

// 24x24 stroke paths (from mockup C)
export const ICON_PATHS = {
  home: "M3 11l9-7 9 7v9a1 1 0 0 1-1 1h-5v-6h-6v6H4a1 1 0 0 1-1-1z",
  ticket: "M4 7h16v3a2 2 0 0 0 0 4v3H4v-3a2 2 0 0 0 0-4zM14 7v10",
  folder: "M3 6h6l2 2h10v11H3z",
  calendar: "M4 6h16v14H4zM4 10h16M8 3v4M16 3v4",
  phone: "M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2",
  clock: "M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18zM12 7v5l3 2",
  receipt: "M6 3h12v18l-3-2-3 2-3-2-3 2zM9 8h6M9 12h6",
  building: "M4 21V4h10v17M14 9h6v12M8 8h2M8 12h2M8 16h2M3 21h18",
  trend: "M3 17l6-6 4 4 8-8M15 7h6v6",
  doc: "M6 3h9l4 4v14H6zM14 3v5h5M9 13h7M9 17h5",
  dollar: "M12 3v18M16 7.5C15.4 6 14 5.5 12 5.5c-2.2 0-4 1-4 3s2 2.8 4 3.3 4 1.4 4 3.4-1.8 3.3-4 3.3c-2 0-3.5-.7-4-2.2",
  cart: "M3 4h2l2.5 11h10L20 7H6.5M9 20h.01M17 20h.01",
  chart: "M4 20V10M10 20V4M16 20v-7M2 20h20",
  shield: "M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z",
  mail: "M3 6h18v12H3zM3 7l9 6 9-6",
  users: "M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM2 21a7 7 0 0 1 14 0M16 3.5a4 4 0 0 1 0 7.5M22 21a7 7 0 0 0-4-6.3",
  user: "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM5 21a7 7 0 0 1 14 0",
  cog: "M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6zM12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9L7 7M17 17l2.1 2.1M4.9 19.1L7 17M17 7l2.1-2.1",
  plug: "M9 3v5M15 3v5M6 8h12v3a6 6 0 0 1-12 0zM12 17v4",
  bolt: "M13 2L4 14h7l-1 8 9-12h-7z",
  link: "M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1",
  key: "M8 15a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM11 11h10M18 11v3M15 11v2",
  list: "M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01",
  search: "M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14zM20 20l-4-4",
  star: "M12 3l2.8 5.7 6.2.9-4.5 4.4 1 6.2L12 17.3 6.5 20.2l1-6.2L3 9.6l6.2-.9z",
  grid: "M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z",
  more: "M5 12h.01M12 12h.01M19 12h.01",
} as const;

export type IconName = keyof typeof ICON_PATHS;

export interface NavItem {
  id: string;
  section: SectionId;
  label: string;
  /** Rail label; always a part of `label`, so the accessible name contains it (WCAG 2.5.3). */
  short: string;
  route: string;
  /** Any one of these opens the page. */
  permission: string | string[];
  /** Also required just to list the page (catalog pages appear under Finance only for roles that
   *  see invoices; techs still reach the catalog from tickets and quotes). */
  listedWith?: string;
  keywords: string[];
  icon: IconName;
}

const INV = "invoice:read";
const PROC = "procurement:read";
const REP = "report:read";

export const NAV_ITEMS: NavItem[] = [
  // Service desk
  { id: "dashboard", section: "service", label: "Dashboard", short: "Dashboard", route: "/dashboard", permission: "ticket:read", keywords: ["home", "overview"], icon: "home" },
  { id: "tickets", section: "service", label: "Tickets", short: "Tickets", route: "/tickets", permission: "ticket:read", keywords: ["queue", "issues", "helpdesk"], icon: "ticket" },
  { id: "projects", section: "service", label: "Projects", short: "Projects", route: "/projects", permission: "ticket:read", keywords: ["jobs", "tasks"], icon: "folder" },
  // Scheduling
  { id: "dispatch", section: "scheduling", label: "Dispatch", short: "Dispatch", route: "/dispatch", permission: "schedule:read", keywords: ["calendar", "board", "appointments"], icon: "calendar" },
  { id: "oncall", section: "scheduling", label: "On-call", short: "On-call", route: "/oncall", permission: "schedule:read", keywords: ["rota", "rotation", "after hours"], icon: "phone" },
  { id: "timesheet", section: "scheduling", label: "My timesheet", short: "Timesheet", route: "/timesheet", permission: "time:write", keywords: ["hours", "time"], icon: "clock" },
  { id: "expenses", section: "scheduling", label: "My expenses", short: "Expenses", route: "/expenses", permission: "time:write", keywords: ["mileage", "receipts"], icon: "receipt" },
  // Clients & sales
  { id: "organizations", section: "clients", label: "Organizations", short: "Organizations", route: "/organizations", permission: "org:read", keywords: ["clients", "customers", "companies", "contacts"], icon: "building" },
  { id: "pipeline", section: "clients", label: "Pipeline", short: "Pipeline", route: "/crm/pipeline", permission: "crm:read", keywords: ["sales", "crm", "opportunities", "deals"], icon: "trend" },
  { id: "leads", section: "clients", label: "Leads", short: "Leads", route: "/crm/leads", permission: "crm:read", keywords: ["sales", "crm", "prospects"], icon: "trend" },
  { id: "forecast", section: "clients", label: "Forecast", short: "Forecast", route: "/crm/forecast", permission: "crm:read", keywords: ["sales", "crm"], icon: "trend" },
  { id: "renewals", section: "clients", label: "Renewals", short: "Renewals", route: "/crm/renewals", permission: "crm:read", keywords: ["sales", "crm", "contracts"], icon: "trend" },
  { id: "quotes", section: "clients", label: "Quotes", short: "Quotes", route: "/quotes", permission: "quote:read", keywords: ["proposals", "surveys"], icon: "doc" },
  { id: "rate-card", section: "clients", label: "Rate card", short: "Rate card", route: "/quotes/rates", permission: "quote:read", keywords: ["quote prices"], icon: "doc" },
  // Finance
  { id: "runs", section: "finance", label: "Monthly runs", short: "Monthly runs", route: "/billing/runs", permission: INV, keywords: ["billing", "invoice run"], icon: "dollar" },
  { id: "invoices", section: "finance", label: "Invoices", short: "Invoices", route: "/billing/invoices", permission: INV, keywords: ["billing", "bills"], icon: "dollar" },
  { id: "receivables", section: "finance", label: "Receivables", short: "Receivables", route: "/billing/receivables", permission: INV, keywords: ["billing", "overdue", "ar", "statements"], icon: "dollar" },
  { id: "client-emails", section: "finance", label: "Client emails", short: "Client emails", route: "/billing/reminders", permission: INV, keywords: ["billing", "reminders", "notices", "statements"], icon: "mail" },
  { id: "payments", section: "finance", label: "Payments", short: "Payments", route: "/billing/payments", permission: INV, keywords: ["billing", "record payment"], icon: "dollar" },
  { id: "credit-memos", section: "finance", label: "Credit memos", short: "Credit memos", route: "/billing/credit-memos", permission: INV, keywords: ["billing", "refunds", "write-offs"], icon: "dollar" },
  { id: "late-fees", section: "finance", label: "Late fees", short: "Late fees", route: "/billing/late-fees", permission: INV, keywords: ["billing", "overdue"], icon: "dollar" },
  { id: "agreements", section: "finance", label: "Agreements", short: "Agreements", route: "/billing/agreements", permission: "billing:read", listedWith: INV, keywords: ["billing", "contracts", "recurring"], icon: "doc" },
  { id: "products", section: "finance", label: "Products", short: "Products", route: "/billing/products", permission: "billing:read", listedWith: INV, keywords: ["billing", "catalog", "parts"], icon: "cart" },
  { id: "rates", section: "finance", label: "Rates", short: "Rates", route: "/billing/rates", permission: "billing:read", listedWith: INV, keywords: ["billing", "work types", "prices"], icon: "dollar" },
  { id: "billing-reports", section: "finance", label: "Billing reports", short: "Billing reports", route: "/billing/reports", permission: INV, listedWith: REP, keywords: ["revenue", "exports", "csv"], icon: "chart" },
  { id: "purchase-orders", section: "finance", label: "Orders and vendors", short: "Orders", route: "/procurement", permission: PROC, keywords: ["procurement", "purchase orders", "po", "vendors", "suppliers"], icon: "cart" },
  { id: "inventory", section: "finance", label: "Inventory", short: "Inventory", route: "/procurement/inventory", permission: PROC, keywords: ["procurement", "stock"], icon: "cart" },
  { id: "markup-rules", section: "finance", label: "Markup rules", short: "Markup", route: "/procurement/markup", permission: PROC, keywords: ["procurement", "pricing"], icon: "cart" },
  // Reports
  { id: "sla", section: "reports", label: "SLA report", short: "SLA", route: "/reports/sla", permission: REP, keywords: ["response", "resolution"], icon: "chart" },
  { id: "utilisation", section: "reports", label: "Utilisation report", short: "Utilisation", route: "/reports/utilisation", permission: REP, keywords: ["utilization", "billable", "capacity"], icon: "chart" },
  { id: "aging", section: "reports", label: "Aging report", short: "Aging", route: "/reports/aging", permission: REP, keywords: ["ageing", "overdue", "receivables"], icon: "chart" },
  { id: "profitability", section: "reports", label: "Profitability report", short: "Profitability", route: "/reports/profitability", permission: REP, keywords: ["margin", "profit"], icon: "chart" },
  { id: "report-schedules", section: "reports", label: "Report schedules", short: "Schedules", route: "/reports/schedules", permission: REP, keywords: ["email reports"], icon: "mail" },
  { id: "warranty", section: "reports", label: "Warranty", short: "Warranty", route: "/warranty", permission: REP, keywords: ["devices", "expiring"], icon: "shield" },
  // Admin
  { id: "users", section: "admin", label: "Users", short: "Users", route: "/admin/users", permission: "user:manage", keywords: ["staff", "team", "roles"], icon: "users" },
  { id: "settings", section: "admin", label: "Settings", short: "Settings", route: "/admin/settings", permission: ["config:manage", "service:configure"], keywords: ["configuration", "queues", "sla", "mail"], icon: "cog" },
  { id: "integrations", section: "admin", label: "Integrations", short: "Integrations", route: "/integrations", permission: "integration:manage", keywords: ["connections", "rmm", "hudu"], icon: "plug" },
  { id: "automation", section: "admin", label: "Automation", short: "Automation", route: "/automation", permission: "automation:manage", keywords: ["rules", "workflows"], icon: "bolt" },
  { id: "webhooks", section: "admin", label: "Webhooks", short: "Webhooks", route: "/webhooks", permission: "automation:manage", keywords: ["events", "outbound"], icon: "link" },
  { id: "api-keys", section: "admin", label: "API keys", short: "API keys", route: "/api-keys", permission: "apikey:manage", keywords: ["tokens"], icon: "key" },
  { id: "audit", section: "admin", label: "Audit log", short: "Audit", route: "/audit", permission: "audit:read", keywords: ["history", "changes"], icon: "list" },
];

const BY_ID = new Map(NAV_ITEMS.map((i) => [i.id, i]));
export const navItem = (id: string) => BY_ID.get(id);

export function canOpen(me: Me | null | undefined, item: NavItem): boolean {
  const any = typeof item.permission === "string" ? [item.permission] : item.permission;
  return any.some((p) => can(me, p)) && (!item.listedWith || can(me, item.listedWith));
}

export const visibleItems = (me: Me | null | undefined) => NAV_ITEMS.filter((i) => canOpen(me, i));

/** Sections with the pages this person may open; an empty section is left out. */
export function visibleSections(me: Me | null | undefined): (NavSection & { items: NavItem[] })[] {
  const items = visibleItems(me);
  return NAV_SECTIONS.map((s) => ({ ...s, items: items.filter((i) => i.section === s.id) })).filter((s) => s.items.length > 0);
}

export const allRoutes = () => NAV_ITEMS.map((i) => i.route);

/** The nav item a URL belongs to: the longest route that is the path or a parent of it. */
export function itemForPath(pathname: string): NavItem | undefined {
  let best: NavItem | undefined;
  for (const i of NAV_ITEMS)
    if ((pathname === i.route || pathname.startsWith(`${i.route}/`)) && (!best || i.route.length > best.route.length)) best = i;
  return best;
}

/** Rail bookmarks until the person changes them (DECISIONS.md, README mockup C, no Knowledge base). */
export const DEFAULT_BOOKMARKS: Record<Role, string[]> = {
  admin: ["dashboard", "tickets", "pipeline", "sla", "settings"],
  manager: ["dashboard", "tickets", "dispatch", "timesheet", "sla"],
  tech: ["tickets", "dispatch", "timesheet", "organizations"],
  billing: ["organizations", "invoices", "receivables", "runs", "aging"],
  read_only: ["tickets", "organizations"],
};
