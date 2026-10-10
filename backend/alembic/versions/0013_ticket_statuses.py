"""Parity phase 1C (part 1): editable ticket statuses mapped to the five built-in behaviours

tickets.status keeps meaning "behaviour" (SLA, reopen, dashboards all read it). tickets.status_id
says which named status the person sees. A trigger keeps the two consistent.

Revision ID: 0013
Revises: 0012
"""
import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
APP_ROLE = "psa_app"
BEHAVIORS = "('new','open','waiting_on_customer','resolved','closed')"
BUILTIN = [
    ("New", "new"),
    ("Open", "open"),
    ("Waiting on customer", "waiting_on_customer"),
    ("Resolved", "resolved"),
    ("Closed", "closed"),
]


def upgrade() -> None:
    op.create_table(
        "ticket_statuses",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("behavior", sa.String(30), nullable=False),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
        sa.CheckConstraint(f"behavior IN {BEHAVIORS}", name="ck_ticket_statuses_behavior"),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_ticket_statuses_name"),
    )
    op.create_index("uq_ticket_statuses_name_active", "ticket_statuses",
                    [sa.text("lower(name)")], unique=True,
                    postgresql_where=sa.text("archived_at IS NULL"))
    for i, (name, behavior) in enumerate(BUILTIN, start=1):
        op.execute(
            sa.text("INSERT INTO ticket_statuses (name, behavior, position) "
                    "VALUES (:n, :b, :p)").bindparams(n=name, b=behavior, p=i * 10)
        )
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON ticket_statuses TO {APP_ROLE}")

    op.execute("""
        CREATE FUNCTION default_status_id(b text) RETURNS bigint LANGUAGE sql STABLE AS $$
            SELECT id FROM ticket_statuses WHERE behavior = b AND archived_at IS NULL
            ORDER BY position, id LIMIT 1
        $$""")
    op.add_column("tickets", sa.Column("status_id", sa.BigInteger,
                                       sa.ForeignKey("ticket_statuses.id")))
    op.execute("UPDATE tickets t SET status_id = default_status_id(t.status)")
    op.alter_column("tickets", "status_id", nullable=False,
                    server_default=sa.text("default_status_id('new')"))
    op.create_index("ix_tickets_status_id", "tickets", ["status_id"])

    op.execute("""
        CREATE FUNCTION tickets_status_consistent() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF (SELECT behavior FROM ticket_statuses WHERE id = NEW.status_id) IS DISTINCT FROM NEW.status THEN
                RAISE EXCEPTION 'ticket status_id does not match its status behaviour'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END $$""")
    op.execute("""
        CREATE TRIGGER trg_tickets_status_consistent BEFORE INSERT OR UPDATE OF status, status_id
        ON tickets FOR EACH ROW EXECUTE FUNCTION tickets_status_consistent()""")


def downgrade() -> None:
    op.execute("DROP TRIGGER trg_tickets_status_consistent ON tickets")
    op.execute("DROP FUNCTION tickets_status_consistent()")
    op.drop_index("ix_tickets_status_id", "tickets")
    op.drop_column("tickets", "status_id")
    op.execute("DROP FUNCTION default_status_id(text)")
    op.drop_table("ticket_statuses")
