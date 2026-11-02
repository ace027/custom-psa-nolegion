"""Manager role; split invoice:read from billing:read and service:configure from config:manage

Revision ID: 0039
Revises: 0038

Owner decisions (phase 16, DECISIONS.md):
- users.role may be 'manager' (service manager: dispatch, approvals, reports, service settings).
- billing:read now covers only the catalog; invoices, payments, statements, notices, credit memos,
  late fees and receivables need invoice:read. Queue, category, priority, status, work type and
  holiday edits need service:configure instead of config:manage.

Role permissions live in code. API keys store their own list, so every key holding billing:read
gains invoice:read and every key holding config:manage gains service:configure: existing keys keep
their effective access. A key is still limited to its owner's role at request time, so a tech's
key gains nothing (techs no longer have invoice:read).

Downgrade removes the two new strings from keys and refuses while any user has role 'manager'.
"""

import sqlalchemy as sa

from alembic import op

revision = "0039"
down_revision = "0038"

ROLES_OLD = "role IN ('admin','tech','billing','read_only')"
ROLES_NEW = "role IN ('admin','manager','tech','billing','read_only')"
# (permission already held, permission added alongside it)
SPLITS = (("billing:read", "invoice:read"), ("config:manage", "service:configure"))


def upgrade() -> None:
    op.drop_constraint("ck_users_role", "users", type_="check")
    op.create_check_constraint("ck_users_role", "users", ROLES_NEW)
    for held, added in SPLITS:
        # keep the list sorted and unique, as the API stores it
        op.execute(
            sa.text(
                "UPDATE api_keys SET permissions = ARRAY(SELECT DISTINCT p FROM"
                " unnest(array_append(permissions, CAST(:added AS varchar))) AS p ORDER BY p)"
                " WHERE CAST(:held AS varchar) = ANY(permissions)"
            ).bindparams(held=held, added=added)
        )


def downgrade() -> None:
    bind = op.get_bind()
    n = bind.execute(sa.text("SELECT count(*) FROM users WHERE role = 'manager'")).scalar_one()
    if n:
        raise RuntimeError(
            f"cannot downgrade 0039: {n} user(s) have the manager role; change their role first"
        )
    op.execute(
        "UPDATE api_keys SET permissions = array_remove(array_remove(permissions, 'invoice:read'),"
        " 'service:configure') WHERE permissions && ARRAY['invoice:read', 'service:configure']"
        "::varchar[]"
    )
    op.drop_constraint("ck_users_role", "users", type_="check")
    op.create_check_constraint("ck_users_role", "users", ROLES_OLD)
