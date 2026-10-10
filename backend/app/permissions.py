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
BILLING_READ = "billing:read"  # agreements, products, rates, charges, invoices, runs
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
CONFIG_MANAGE = "config:manage"  # queues, categories, priorities, work types, settings, mail status
SCHEDULE_READ = "schedule:read"  # schedules, appointments, availability, time off
# book/move/cancel any tech's appointments; own working hours and time-off requests
SCHEDULE_WRITE = "schedule:write"
TIMEOFF_APPROVE = "timeoff:approve"  # approve/reject time off, manage anyone's hours and time off

ROLES = ("admin", "tech", "billing", "read_only")

_READ = {ORG_READ, USER_READ, TICKET_READ, BILLING_READ, QUOTE_READ, SCHEDULE_READ}

MATRIX: dict[str, frozenset[str]] = {
    "admin": frozenset(
        _READ
        | {
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
        }
        | {BILLING_WRITE, BILLING_FINALIZE, CHARGE_WRITE, PAYMENT_WRITE, REPORT_READ}
    ),
    "tech": frozenset(
        _READ | {ORG_WRITE, TICKET_WRITE, TIME_WRITE, CHARGE_WRITE, QUOTE_WRITE, SCHEDULE_WRITE}
    ),
    "billing": frozenset(
        _READ | {BILLING_WRITE, BILLING_FINALIZE, CHARGE_WRITE, PAYMENT_WRITE, REPORT_READ}
    ),
    "read_only": frozenset(_READ),
}


def has_permission(role: str, permission: str) -> bool:
    return permission in MATRIX.get(role, frozenset())
