"""Procurement: vendors, purchase orders and lines, inventory, markup rules

Revision ID: 0031
Revises: 0030

All five new tables are staff-internal (no organization-owned rows in the RLS sense, no RLS);
organization_id on purchase orders and inventory only records who the goods are for. Also adds
products.category and settings.default_markup_bp.
"""

import sqlalchemy as sa

from alembic import op

revision = "0031"
down_revision = "0030"
APP_ROLE = "psa_app"
NOW = sa.text("now()")
TABLES = ("vendors", "purchase_orders", "purchase_order_lines", "inventory_items", "markup_rules")
CATEGORIES = "('hardware','software','license','other')"


def _stamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
    ]


def upgrade() -> None:
    op.add_column("products", sa.Column("category", sa.String(10)))
    op.create_check_constraint(
        "ck_products_category", "products", f"category IS NULL OR category IN {CATEGORIES}"
    )
    op.add_column(
        "settings",
        sa.Column("default_markup_bp", sa.Integer, nullable=False, server_default="0"),
    )
    op.create_check_constraint(
        "ck_settings_default_markup", "settings", "default_markup_bp BETWEEN 0 AND 100000"
    )

    op.create_table(
        "vendors",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("account_number", sa.String(64)),
        sa.Column("email", sa.String(320)),
        sa.Column("phone", sa.String(40)),
        sa.Column("website", sa.String(300)),
        sa.Column("notes", sa.Text),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
        *_stamps(),
    )
    op.execute("CREATE UNIQUE INDEX uq_vendors_name ON vendors (lower(name))")

    op.create_table(
        "purchase_orders",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        # 'PO-<id>' is set by the service right after the insert
        sa.Column("number", sa.String(20)),
        sa.Column("vendor_id", sa.BigInteger, sa.ForeignKey("vendors.id"), nullable=False),
        sa.Column("organization_id", sa.BigInteger, sa.ForeignKey("organizations.id")),
        sa.Column("status", sa.String(10), nullable=False, server_default="draft"),
        sa.Column("ordered_on", sa.Date),
        sa.Column("expected_on", sa.Date),
        sa.Column("vendor_reference", sa.String(100)),
        sa.Column("notes", sa.Text),
        sa.Column("created_by", sa.BigInteger, sa.ForeignKey("users.id")),
        *_stamps(),
        sa.CheckConstraint(
            "status IN ('draft','ordered','partial','received','cancelled')",
            name="ck_purchase_orders_status",
        ),
        sa.UniqueConstraint("number", name="uq_purchase_orders_number"),
    )
    op.create_index("ix_purchase_orders_vendor", "purchase_orders", ["vendor_id"])
    op.create_index("ix_purchase_orders_status", "purchase_orders", ["status"])

    op.create_table(
        "purchase_order_lines",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column(
            "purchase_order_id",
            sa.BigInteger,
            sa.ForeignKey("purchase_orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer, nullable=False, server_default="0"),
        sa.Column("product_id", sa.BigInteger, sa.ForeignKey("products.id")),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("quantity", sa.Integer, nullable=False),
        sa.Column("unit_cost_cents", sa.BigInteger, nullable=False),
        sa.Column("received_quantity", sa.Integer, nullable=False, server_default="0"),
        sa.Column("serialised", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("billable", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("taxable", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("markup_bp", sa.Integer),
        *_stamps(),
        sa.CheckConstraint("quantity > 0", name="ck_po_lines_quantity"),
        sa.CheckConstraint("unit_cost_cents >= 0", name="ck_po_lines_cost"),
        sa.CheckConstraint(
            "received_quantity >= 0 AND received_quantity <= quantity", name="ck_po_lines_received"
        ),
        sa.CheckConstraint(
            "markup_bp IS NULL OR markup_bp BETWEEN 0 AND 100000", name="ck_po_lines_markup"
        ),
    )
    op.create_index("ix_po_lines_po", "purchase_order_lines", ["purchase_order_id"])

    op.create_table(
        "inventory_items",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column(
            "purchase_order_line_id", sa.BigInteger, sa.ForeignKey("purchase_order_lines.id")
        ),
        sa.Column("product_id", sa.BigInteger, sa.ForeignKey("products.id")),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("serial_number", sa.String(120)),
        sa.Column("quantity", sa.Integer, nullable=False),
        sa.Column("unit_cost_cents", sa.BigInteger, nullable=False),
        sa.Column("status", sa.String(10), nullable=False, server_default="in_stock"),
        sa.Column("organization_id", sa.BigInteger, sa.ForeignKey("organizations.id")),
        sa.Column("asset_id", sa.BigInteger, sa.ForeignKey("assets.id")),
        sa.Column("delivered_on", sa.Date),
        sa.Column("markup_bp", sa.Integer),
        sa.Column(
            "product_charge_id", sa.BigInteger, sa.ForeignKey("product_charges.id"), unique=True
        ),
        sa.Column("received_on", sa.Date, nullable=False),
        sa.Column("notes", sa.Text),
        *_stamps(),
        sa.CheckConstraint("quantity > 0", name="ck_inventory_quantity"),
        sa.CheckConstraint("serial_number IS NULL OR quantity = 1", name="ck_inventory_serial_qty"),
        sa.CheckConstraint("unit_cost_cents >= 0", name="ck_inventory_cost"),
        sa.CheckConstraint(
            "status IN ('in_stock','delivered','consumed')", name="ck_inventory_status"
        ),
        sa.CheckConstraint(
            "status <> 'delivered' OR (organization_id IS NOT NULL AND delivered_on IS NOT NULL)",
            name="ck_inventory_delivered",
        ),
        sa.CheckConstraint(
            "markup_bp IS NULL OR markup_bp BETWEEN 0 AND 100000", name="ck_inventory_markup"
        ),
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_inventory_serial ON inventory_items (lower(serial_number)) "
        "WHERE serial_number IS NOT NULL"
    )
    op.create_index("ix_inventory_status", "inventory_items", ["status"])
    op.create_index("ix_inventory_org", "inventory_items", ["organization_id"])

    op.create_table(
        "markup_rules",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("product_id", sa.BigInteger, sa.ForeignKey("products.id")),
        sa.Column("category", sa.String(10)),
        sa.Column("markup_bp", sa.Integer, nullable=False),
        *_stamps(),
        sa.CheckConstraint(f"category IN {CATEGORIES}", name="ck_markup_rules_category"),
        sa.CheckConstraint("markup_bp BETWEEN 0 AND 100000", name="ck_markup_rules_markup"),
        sa.CheckConstraint(
            "(product_id IS NULL) <> (category IS NULL)", name="ck_markup_rules_target"
        ),
        sa.UniqueConstraint("product_id", name="uq_markup_rules_product"),
        sa.UniqueConstraint("category", name="uq_markup_rules_category"),
    )

    for table in TABLES:
        op.execute(f"GRANT SELECT, INSERT, UPDATE ON {table} TO {APP_ROLE}")
    op.execute(f"GRANT DELETE ON purchase_order_lines, markup_rules TO {APP_ROLE}")
    op.execute(f"GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}")


def downgrade() -> None:
    op.drop_table("markup_rules")
    op.drop_table("inventory_items")
    op.drop_table("purchase_order_lines")
    op.drop_table("purchase_orders")
    op.drop_table("vendors")
    op.drop_constraint("ck_settings_default_markup", "settings", type_="check")
    op.drop_column("settings", "default_markup_bp")
    op.drop_constraint("ck_products_category", "products", type_="check")
    op.drop_column("products", "category")
