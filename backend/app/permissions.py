"""The one place that says what each role may do. Default is deny."""

ORG_READ = "org:read"
ORG_WRITE = "org:write"  # organizations, sites, contacts
USER_READ = "user:read"
USER_MANAGE = "user:manage"
AUDIT_READ = "audit:read"
TICKET_READ = "ticket:read"  # tickets, notes, time entries, queues/categories/priorities/settings
TICKET_WRITE = "ticket:write"  # tickets and notes
TIME_WRITE = "time:write"
BILLING_READ = "billing:read"  # agreements, products, rates, charges, invoices, runs
BILLING_WRITE = "billing:write"  # edit those, and DRAFT invoices
BILLING_FINALIZE = "billing:finalize"  # finalize / void invoices, review and finalize runs
PAYMENT_WRITE = "payment:write"  # record payments, apply them to invoices, unapply
CHARGE_WRITE = "charge:write"  # add/void one-off product charges (techs may sell parts)
CONFIG_MANAGE = "config:manage"  # queues, categories, priorities, work types, settings, mail status

ROLES = ("admin", "tech", "billing", "read_only")

_READ = {ORG_READ, USER_READ, TICKET_READ, BILLING_READ}

MATRIX: dict[str, frozenset[str]] = {
    "admin": frozenset(
        _READ
        | {ORG_WRITE, USER_MANAGE, AUDIT_READ, TICKET_WRITE, TIME_WRITE, CONFIG_MANAGE}
        | {BILLING_WRITE, BILLING_FINALIZE, CHARGE_WRITE, PAYMENT_WRITE}
    ),
    "tech": frozenset(_READ | {ORG_WRITE, TICKET_WRITE, TIME_WRITE, CHARGE_WRITE}),
    "billing": frozenset(_READ | {BILLING_WRITE, BILLING_FINALIZE, CHARGE_WRITE, PAYMENT_WRITE}),
    "read_only": frozenset(_READ),
}


def has_permission(role: str, permission: str) -> bool:
    return permission in MATRIX.get(role, frozenset())
