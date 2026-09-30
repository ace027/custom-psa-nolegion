"""The one place that says what each role may do. Default is deny."""

ORG_READ = "org:read"
ORG_WRITE = "org:write"  # organizations, sites, contacts
USER_READ = "user:read"
USER_MANAGE = "user:manage"
AUDIT_READ = "audit:read"

ROLES = ("admin", "tech", "billing", "read_only")

_READ = {ORG_READ, USER_READ}

MATRIX: dict[str, frozenset[str]] = {
    "admin": frozenset(_READ | {ORG_WRITE, USER_MANAGE, AUDIT_READ}),
    "tech": frozenset(_READ | {ORG_WRITE}),
    "billing": frozenset(_READ),  # gains contract/invoice permissions in Phase 3
    "read_only": frozenset(_READ),
}


def has_permission(role: str, permission: str) -> bool:
    return permission in MATRIX.get(role, frozenset())
