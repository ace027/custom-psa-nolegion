"""Procurement schema guards (migration 0031): CHECKs, serial uniqueness, privileges, defaults."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.procurement_schemas import MarkupRuleIn, ReceiveIn

NEW = ("vendors", "purchase_orders", "purchase_order_lines", "inventory_items", "markup_rules")


def add(owner, table, **cols):
    names = ", ".join(cols)
    values = ", ".join(f":{c}" for c in cols)
    return owner.execute(
        text(f"INSERT INTO {table} ({names}) VALUES ({values}) RETURNING id"), cols
    ).scalar_one()


def add_vendor(owner, name="Acme Supply"):
    return add(owner, "vendors", name=name)


def add_po(owner):
    return add(owner, "purchase_orders", vendor_id=add_vendor(owner))


def add_line(owner, po=None, **kw):
    cols = {
        "purchase_order_id": po or add_po(owner),
        "description": "Switch",
        "quantity": 5,
        "unit_cost_cents": 1000,
        **kw,
    }
    return add(owner, "purchase_order_lines", **cols)


def add_item(owner, **kw):
    cols = {
        "description": "Switch",
        "quantity": 1,
        "unit_cost_cents": 1000,
        "received_on": "2026-01-01",
        **kw,
    }
    return add(owner, "inventory_items", **cols)


def add_product(owner, **kw):
    cols = {"name": "Widget", "unit_price_cents": 100, **kw}
    return add(owner, "products", **cols)


def test_vendor_name_unique_case_insensitive(owner):
    add_vendor(owner, "Ingram")
    with pytest.raises(IntegrityError, match="uq_vendors_name"):
        add_vendor(owner, "INGRAM")


def test_po_defaults_and_checks(owner):
    po = add_po(owner)
    assert owner.execute(
        text("SELECT status, number FROM purchase_orders WHERE id = :i"), {"i": po}
    ).one() == ("draft", None)
    with pytest.raises(IntegrityError, match="ck_purchase_orders_status"):
        add(owner, "purchase_orders", vendor_id=add_vendor(owner, "V2"), status="open")
    add(owner, "purchase_orders", vendor_id=add_vendor(owner, "V3"), number="PO-1")
    with pytest.raises(IntegrityError, match="uq_purchase_orders_number"):
        add(owner, "purchase_orders", vendor_id=add_vendor(owner, "V4"), number="PO-1")


def test_line_checks(owner):
    po = add_po(owner)
    add_line(owner, po)
    with pytest.raises(IntegrityError, match="ck_po_lines_quantity"):
        add_line(owner, po, quantity=0)
    with pytest.raises(IntegrityError, match="ck_po_lines_cost"):
        add_line(owner, po, unit_cost_cents=-1)
    with pytest.raises(IntegrityError, match="ck_po_lines_received"):
        add_line(owner, po, received_quantity=6)
    with pytest.raises(IntegrityError, match="ck_po_lines_received"):
        add_line(owner, po, received_quantity=-1)
    add_line(owner, po, received_quantity=5)
    for bad in (-1, 100001):
        with pytest.raises(IntegrityError, match="ck_po_lines_markup"):
            add_line(owner, po, markup_bp=bad)
    add_line(owner, po, markup_bp=0)
    add_line(owner, po, markup_bp=100000)
    row = owner.execute(
        text(
            "SELECT serialised, billable, taxable, received_quantity FROM purchase_order_lines "
            "ORDER BY id LIMIT 1"
        )
    ).one()
    assert row == (False, True, True, 0)


def test_line_cascades_with_order(owner):
    po = add_po(owner)
    add_line(owner, po)
    owner.execute(text("DELETE FROM purchase_orders WHERE id = :i"), {"i": po})
    assert owner.execute(text("SELECT count(*) FROM purchase_order_lines")).scalar_one() == 0


def test_serial_unique_case_insensitive(owner):
    add_item(owner, serial_number="SN-abc")
    with pytest.raises(IntegrityError, match="uq_inventory_serial"):
        add_item(owner, serial_number="sn-ABC")
    add_item(owner, serial_number="SN-other")
    add_item(owner)  # non-serialised items may repeat
    add_item(owner)


def test_serialised_item_quantity_one(owner):
    with pytest.raises(IntegrityError, match="ck_inventory_serial_qty"):
        add_item(owner, serial_number="SN-1", quantity=2)
    add_item(owner, quantity=5)  # non-serialised stock may be bulk
    with pytest.raises(IntegrityError, match="ck_inventory_quantity"):
        add_item(owner, quantity=0)
    with pytest.raises(IntegrityError, match="ck_inventory_cost"):
        add_item(owner, unit_cost_cents=-1)


def test_inventory_status_and_delivery(owner, make_org):
    org = make_org("Acme")["id"]
    row = owner.execute(
        text("SELECT status FROM inventory_items WHERE id = :i"), {"i": add_item(owner)}
    ).one()
    assert row == ("in_stock",)
    with pytest.raises(IntegrityError, match="ck_inventory_status"):
        add_item(owner, status="lost")
    with pytest.raises(IntegrityError, match="ck_inventory_delivered"):
        add_item(owner, status="delivered")
    with pytest.raises(IntegrityError, match="ck_inventory_delivered"):
        add_item(owner, status="delivered", organization_id=org)
    with pytest.raises(IntegrityError, match="ck_inventory_delivered"):
        add_item(owner, status="delivered", delivered_on="2026-02-01")
    add_item(owner, status="delivered", organization_id=org, delivered_on="2026-02-01")
    add_item(owner, status="in_stock", organization_id=org)  # reserved
    for bad in (-1, 100001):
        with pytest.raises(IntegrityError, match="ck_inventory_markup"):
            add_item(owner, markup_bp=bad)


def test_markup_rule_needs_exactly_one_target(owner):
    prod = add_product(owner)
    with pytest.raises(IntegrityError, match="ck_markup_rules_target"):
        add(owner, "markup_rules", markup_bp=100)
    with pytest.raises(IntegrityError, match="ck_markup_rules_target"):
        add(owner, "markup_rules", markup_bp=100, product_id=prod, category="hardware")
    add(owner, "markup_rules", markup_bp=100, product_id=prod)
    add(owner, "markup_rules", markup_bp=100, category="hardware")
    with pytest.raises(IntegrityError, match="uq_markup_rules_product"):
        add(owner, "markup_rules", markup_bp=200, product_id=prod)
    with pytest.raises(IntegrityError, match="uq_markup_rules_category"):
        add(owner, "markup_rules", markup_bp=200, category="hardware")
    with pytest.raises(IntegrityError, match="ck_markup_rules_category"):
        add(owner, "markup_rules", markup_bp=100, category="gadgets")


def test_markup_rule_bounds(owner):
    for bad in (-1, 100001):
        with pytest.raises(IntegrityError, match="ck_markup_rules_markup"):
            add(owner, "markup_rules", markup_bp=bad, category="software")
    add(owner, "markup_rules", markup_bp=0, category="software")
    add(owner, "markup_rules", markup_bp=100000, category="license")


def test_product_category_check(owner):
    with pytest.raises(IntegrityError, match="ck_products_category"):
        add_product(owner, category="gadgets")
    for ok in ("hardware", "software", "license", "other", None):
        add_product(owner, category=ok)


def test_settings_default_markup(owner):
    assert owner.execute(text("SELECT default_markup_bp FROM settings")).scalar_one() == 0
    with pytest.raises(IntegrityError, match="ck_settings_default_markup"):
        owner.execute(text("UPDATE settings SET default_markup_bp = 100001"))
    with pytest.raises(IntegrityError, match="ck_settings_default_markup"):
        owner.execute(text("UPDATE settings SET default_markup_bp = -1"))
    owner.execute(text("UPDATE settings SET default_markup_bp = 2500"))


def test_runtime_role_privileges(owner):
    for table in NEW:
        for p in ("SELECT", "INSERT", "UPDATE", "DELETE"):
            has = owner.execute(
                text("SELECT has_table_privilege('psa_app', :t, :p)"), {"t": table, "p": p}
            ).scalar_one()
            can_delete = table in ("purchase_order_lines", "markup_rules")
            assert has == (p != "DELETE" or can_delete), (table, p)


def test_no_rls_on_new_tables(owner):
    for table in NEW:
        row = owner.execute(
            text("SELECT relrowsecurity FROM pg_class WHERE relname = :t"), {"t": table}
        ).one()
        assert row == (False,), table


def test_receive_in_serials_validation():
    ok = ReceiveIn(line_id=1, quantity=2, serials=[" A1 ", "B2"])
    assert ok.serials == ["A1", "B2"]
    with pytest.raises(ValueError):
        ReceiveIn(line_id=1, quantity=2, serials=["A1", "a1"])
    with pytest.raises(ValueError):
        ReceiveIn(line_id=1, quantity=2, serials=["A1", "  "])
    with pytest.raises(ValueError):
        ReceiveIn(line_id=1, quantity=0)


def test_markup_rule_in_validation():
    MarkupRuleIn(category="hardware", markup_bp=100)
    MarkupRuleIn(product_id=3, markup_bp=0)
    with pytest.raises(ValueError):
        MarkupRuleIn(markup_bp=100)
    with pytest.raises(ValueError):
        MarkupRuleIn(product_id=1, category="hardware", markup_bp=100)
    with pytest.raises(ValueError):
        MarkupRuleIn(category="hardware", markup_bp=100001)
    with pytest.raises(ValueError):
        MarkupRuleIn(category="gadgets", markup_bp=1)
