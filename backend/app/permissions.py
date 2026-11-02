"""The one place that says what each role may do. Default is deny."""

ORG_READ = "org:read"
ORG_WRITE = "org:write"  # organizations, sites, contacts
USER_READ = "user:read"
USER_MANAGE = "user:manage"
AUDIT_READ = "audit:read"
TICKET_READ = "ticket:read"  # tickets, notes, time entries, queues/categories/priorities/settings
TICKET_WRITE = "ticket:write"  # tickets and notes
TIME_WRITE = "time:write"
TIMESHEET_APPROVE = "timesheet:approve"  # approve / return timesheets, payroll export (admins)
BILLING_READ = "billing:read"  # the catalog: agreements, products, rates, ticket charges
# invoices, runs, payments, statements, reminders/notices, credit memos, write-offs, late fees,
# receivables (finance; not for techs or read-only)
INVOICE_READ = "invoice:read"
BILLING_WRITE = "billing:write"  # edit those, and DRAFT invoices
BILLING_FINALIZE = "billing:finalize"  # finalize / void invoices, review and finalize runs
PAYMENT_WRITE = "payment:write"  # record payments, apply them to invoices, unapply
CHARGE_WRITE = "charge:write"  # add/void one-off product charges (techs may sell parts)
REPORT_READ = "report:read"  # billing reports and CSV exports (revenue is sensitive: not for techs)
PORTAL_MANAGE = (
    "portal:manage"  # grant a contact client-portal access (turning it off needs only org:write)
)
QUOTE_READ = "quote:read"  # surveys, quotes, the rate card
QUOTE_WRITE = "quote:write"  # run surveys, build / adjust / send quotes (techs)
QUOTE_MANAGE = "quote:manage"  # approve adjusted prices, record accept/decline, edit the rate card
INTEGRATION_MANAGE = "integration:manage"  # vendor connections, credentials, client mapping
CONFIG_MANAGE = "config:manage"  # general settings: mail, billing, portal, security, CRM stages
# service settings: queues, categories, priorities (SLA), statuses, work types, holidays
SERVICE_CONFIGURE = "service:configure"
SCHEDULE_READ = "schedule:read"  # schedules, appointments, availability, time off
# book/move/cancel any tech's appointments; own working hours and time-off requests
SCHEDULE_WRITE = "schedule:write"
TIMEOFF_APPROVE = "timeoff:approve"  # approve/reject time off, manage anyone's hours and time off
APIKEY_MANAGE = "apikey:manage"  # create / revoke API keys (admins)
AUTOMATION_MANAGE = "automation:manage"  # automation rules and outbound webhooks (admins)
# projects, phases, tasks, dependencies; billing fields need billing:write
PROJECT_WRITE = "project:write"
CRM_READ = "crm:read"  # leads, opportunities, pipeline, forecast, renewals (every staff role)
CRM_WRITE = "crm:write"  # create / edit / convert leads and opportunities (admin, tech)
PROCUREMENT_READ = "procurement:read"  # vendors, purchase orders, inventory, markup rules
PROCUREMENT_WRITE = "procurement:write"  # edit those, receive stock, deliver to clients

# API keys can never carry these, whatever the owner's role
KEY_FORBIDDEN = frozenset({USER_MANAGE, APIKEY_MANAGE, PORTAL_MANAGE})

ROLES = ("admin", "manager", "tech", "billing", "read_only")

# what every staff role may read; finance (invoice:read) and procurement are granted per role
_READ = {
    ORG_READ,
    USER_READ,
    TICKET_READ,
    BILLING_READ,
    QUOTE_READ,
    SCHEDULE_READ,
    CRM_READ,
}

_TECH = _READ | {
    ORG_WRITE,
    TICKET_WRITE,
    TIME_WRITE,
    CHARGE_WRITE,
    QUOTE_WRITE,
    SCHEDULE_WRITE,
    PROJECT_WRITE,
    CRM_WRITE,
}

MATRIX: dict[str, frozenset[str]] = {
    "admin": frozenset(
        _READ
        | {
            INVOICE_READ,
            PROCUREMENT_READ,
            SERVICE_CONFIGURE,
            ORG_WRITE,
            USER_MANAGE,
            AUDIT_READ,
            TICKET_WRITE,
            TIME_WRITE,
            TIMESHEET_APPROVE,
            CONFIG_MANAGE,
            PORTAL_MANAGE,
            QUOTE_WRITE,
            QUOTE_MANAGE,
            INTEGRATION_MANAGE,
            SCHEDULE_WRITE,
            TIMEOFF_APPROVE,
            APIKEY_MANAGE,
            AUTOMATION_MANAGE,
            PROJECT_WRITE,
            CRM_WRITE,
            PROCUREMENT_WRITE,
        }
        | {BILLING_WRITE, BILLING_FINALIZE, CHARGE_WRITE, PAYMENT_WRITE, REPORT_READ}
    ),
    "manager": frozenset(
        # service manager: tech work plus approvals, reports, audit, read-only invoices and
        # service settings; no billing writes, payments, procurement, admin or general settings
        _TECH
        | {
            TIMESHEET_APPROVE,
            TIMEOFF_APPROVE,
            REPORT_READ,
            AUDIT_READ,
            INVOICE_READ,
            SERVICE_CONFIGURE,
        }
    ),
    "tech": frozenset(_TECH),
    "billing": frozenset(
        _READ
        | {
            INVOICE_READ,
            PROCUREMENT_READ,
            BILLING_WRITE,
            BILLING_FINALIZE,
            CHARGE_WRITE,
            PAYMENT_WRITE,
            REPORT_READ,
            PROCUREMENT_WRITE,
        }
    ),
    "read_only": frozenset(_READ),
}


def has_permission(role: str, permission: str) -> bool:
    return permission in MATRIX.get(role, frozenset())
