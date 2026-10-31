"""Procurement: vendors, the PO lifecycle, receiving with serials, delivery billing, markup
resolution, undoing a delivery and the end-to-end product invoice line."""

from datetime import timedelta

import pytest
from sqlalchemy import text

from tests.conftest import biz_today
from tests.test_timekeeping import audit_actions

P = "/api/v1/procurement"


@pytest.fixture
def tech(login):
    return login("tech")


@pytest.fixture
def vendor(admin):
    r = admin.post(f"{P}/vendors", json={"name": "Ingram"})
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture
def taxed(admin, org_ctx):
    r = admin.patch(f"/api/v1/organizations/{org_ctx['org']}/billing", json={"tax_rate_bp": 825})
    assert r.status_code == 200, r.text


def make_po(c, vendor, lines=None, **kw):
    body = {"vendor_id": vendor["id"], "lines": lines or [], **kw}
    r = c.post(f"{P}/purchase-orders", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def line(**kw):
    return {"description": "Laptop", "quantity": 1, "unit_cost_cents": 12345, **kw}


def ordered_po(c, vendor, lines, **kw):
    po = make_po(c, vendor, lines, **kw)
    r = c.post(f"{P}/purchase-orders/{po['id']}/order")
    assert r.status_code == 200, r.text
    return r.json()


def receive(c, po, idx=0, quantity=1, serials=None):
    return c.post(
        f"{P}/purchase-orders/{po['id']}/receive",
        json={"line_id": po["lines"][idx]["id"], "quantity": quantity, "serials": serials or []},
    )


def stock(c, vendor, quantity=1, serials=None, **kw):
    """An ordered, received PO; -> the inventory items."""
    serial = serials is not None
    po = ordered_po(c, vendor, [line(quantity=quantity, serialised=serial, **kw)])
    r = receive(c, po, quantity=quantity, serials=serials)
    assert r.status_code == 201, r.text
    return r.json()


def deliver(c, item, org, **kw):
    return c.post(f"{P}/inventory/{item['id']}/deliver", json={"organization_id": org, **kw})


def charges(owner):
    rows = owner.execute(
        text(
            "SELECT id, quantity, unit_price_cents, taxable, voided_at, invoice_line_id, "
            "description, product_id FROM product_charges ORDER BY id"
        )
    ).all()
    return rows


def product(admin, **kw):
    body = {"name": "Switch", "unit_price_cents": 99999, "cost_cents": 12345, **kw}
    r = admin.post("/api/v1/products", json=body)
    assert r.status_code == 201, r.text
    return r.json()


# ---- vendors ----------------------------------------------------------------------------------
def test_vendor_crud_archive_and_duplicates(admin, tech, vendor, owner):
    assert admin.post(f"{P}/vendors", json={"name": "INGRAM"}).status_code == 409
    other = admin.post(f"{P}/vendors", json={"name": "CDW", "email": "a@cdw.example"}).json()
    r = admin.patch(f"{P}/vendors/{other['id']}", json={"phone": "555-0100"})
    assert r.status_code == 200 and r.json()["phone"] == "555-0100"
    assert admin.patch(f"{P}/vendors/{other['id']}", json={"name": "ingram"}).status_code == 409
    assert admin.patch(f"{P}/vendors/{other['id']}", json={"archived": True}).status_code == 200
    assert [v["name"] for v in tech.get(f"{P}/vendors").json()] == ["Ingram"]
    names = [v["name"] for v in tech.get(f"{P}/vendors?include_archived=true").json()]
    assert names == ["CDW", "Ingram"]
    assert admin.patch(f"{P}/vendors/999", json={"notes": "x"}).status_code == 404
    acts = audit_actions(owner)
    assert {"vendor.create", "vendor.update", "vendor.archive"} <= set(acts)
    # an archived vendor can't take a new order
    r = admin.post(f"{P}/purchase-orders", json={"vendor_id": other["id"]})
    assert r.status_code == 409


# ---- purchase orders --------------------------------------------------------------------------
def test_order_lifecycle_and_draft_only_edits(admin, vendor, owner):
    po = make_po(admin, vendor, [line()])
    assert po["number"] == f"PO-{po['id']}" and po["status"] == "draft"
    assert po["vendor_name"] == "Ingram" and len(po["lines"]) == 1
    url = f"{P}/purchase-orders/{po['id']}"
    r = admin.post(f"{url}/lines", json=line(description="Dock", quantity=2))
    assert r.status_code == 201 and [x["description"] for x in r.json()["lines"]] == [
        "Laptop",
        "Dock",
    ]
    extra = r.json()["lines"][1]
    r = admin.patch(f"{url}/lines/{extra['id']}", json={"quantity": 3, "markup_bp": 900})
    assert r.status_code == 200
    assert r.json()["lines"][1]["quantity"] == 3 and r.json()["lines"][1]["markup_bp"] == 900
    assert admin.delete(f"{url}/lines/{extra['id']}").status_code == 204
    assert len(admin.get(url).json()["lines"]) == 1
    assert admin.delete(f"{url}/lines/{extra['id']}").status_code == 404
    r = admin.post(f"{url}/order")
    assert r.status_code == 200
    assert r.json()["status"] == "ordered" and r.json()["ordered_on"] == biz_today().isoformat()
    # no longer a draft: lines are frozen, and it can't be ordered twice
    assert admin.post(f"{url}/lines", json=line()).status_code == 409
    first = r.json()["lines"][0]["id"]
    assert admin.patch(f"{url}/lines/{first}", json={"quantity": 9}).status_code == 409
    assert admin.delete(f"{url}/lines/{first}").status_code == 409
    assert admin.post(f"{url}/order").status_code == 409
    assert admin.patch(url, json={"lines": [line()]}).status_code == 409
    assert admin.patch(url, json={"notes": "chase vendor"}).json()["notes"] == "chase vendor"
    acts = audit_actions(owner)
    for a in ("purchase_order.create", "purchase_order.order", "purchase_order.line_add"):
        assert a in acts


def test_order_needs_a_line_and_patch_can_replace_lines(admin, vendor):
    po = make_po(admin, vendor)
    url = f"{P}/purchase-orders/{po['id']}"
    assert admin.post(f"{url}/order").status_code == 409
    r = admin.patch(url, json={"lines": [line(description="A"), line(description="B")]})
    assert r.status_code == 200 and [x["description"] for x in r.json()["lines"]] == ["A", "B"]
    r = admin.patch(url, json={"lines": [line(description="C")]})
    assert [x["description"] for x in r.json()["lines"]] == ["C"]


def test_line_defaults_from_product_and_requires_a_cost(admin, vendor):
    p = product(admin, taxable=False)
    r = admin.post(
        f"{P}/purchase-orders",
        json={"vendor_id": vendor["id"], "lines": [{"product_id": p["id"], "quantity": 2}]},
    )
    assert r.status_code == 201, r.text
    got = r.json()["lines"][0]
    assert (got["description"], got["unit_cost_cents"], got["taxable"]) == ("Switch", 12345, False)
    nocost = admin.post("/api/v1/products", json={"name": "Cable", "unit_price_cents": 500}).json()
    r = admin.post(
        f"{P}/purchase-orders",
        json={"vendor_id": vendor["id"], "lines": [{"product_id": nocost["id"], "quantity": 1}]},
    )
    assert r.status_code == 409 and "cost" in r.json()["detail"].lower()
    # a line without a product needs a description
    r = admin.post(
        f"{P}/purchase-orders",
        json={"vendor_id": vendor["id"], "lines": [{"quantity": 1, "unit_cost_cents": 5}]},
    )
    assert r.status_code == 409
    assert admin.post(f"{P}/purchase-orders", json={"vendor_id": 999}).status_code == 409


def test_cancel_rules(admin, vendor, owner):
    draft = make_po(admin, vendor, [line()])
    assert admin.post(f"{P}/purchase-orders/{draft['id']}/cancel").json()["status"] == "cancelled"
    assert admin.post(f"{P}/purchase-orders/{draft['id']}/cancel").status_code == 409
    assert admin.post(f"{P}/purchase-orders/{draft['id']}/order").status_code == 409
    sent = ordered_po(admin, vendor, [line(quantity=2)])
    assert receive(admin, sent, quantity=1).status_code == 201
    r = admin.post(f"{P}/purchase-orders/{sent['id']}/cancel")
    assert r.status_code == 409  # partially received
    fresh = ordered_po(admin, vendor, [line()])
    assert admin.post(f"{P}/purchase-orders/{fresh['id']}/cancel").status_code == 200
    assert receive(admin, fresh).status_code == 409  # cancelled orders take no goods
    assert "purchase_order.cancel" in audit_actions(owner)


# ---- markup rules and resolution --------------------------------------------------------------
def test_markup_rule_crud_and_duplicates(admin, tech, vendor, owner):
    p = product(admin)
    r = admin.post(f"{P}/markup-rules", json={"category": "hardware", "markup_bp": 2000})
    assert r.status_code == 201, r.text
    rule = r.json()
    assert (
        admin.post(f"{P}/markup-rules", json={"category": "hardware", "markup_bp": 1}).status_code
        == 409
    )
    pr = admin.post(f"{P}/markup-rules", json={"product_id": p["id"], "markup_bp": 500})
    assert pr.status_code == 201
    assert (
        admin.post(f"{P}/markup-rules", json={"product_id": p["id"], "markup_bp": 1}).status_code
        == 409
    )
    assert (
        admin.post(f"{P}/markup-rules", json={"product_id": 999, "markup_bp": 1}).status_code == 409
    )
    assert admin.post(f"{P}/markup-rules", json={"markup_bp": 1}).status_code == 422
    r = admin.patch(f"{P}/markup-rules/{rule['id']}", json={"markup_bp": 2500})
    assert r.status_code == 200 and r.json()["markup_bp"] == 2500
    assert len(tech.get(f"{P}/markup-rules").json()) == 2
    assert admin.delete(f"{P}/markup-rules/{rule['id']}").status_code == 204
    assert admin.delete(f"{P}/markup-rules/{rule['id']}").status_code == 404
    assert {"markup_rule.create", "markup_rule.update", "markup_rule.delete"} <= set(
        audit_actions(owner)
    )


def test_default_markup_setting_and_product_category(admin):
    assert admin.get("/api/v1/settings").json()["default_markup_bp"] == 0
    r = admin.patch("/api/v1/settings", json={"default_markup_bp": 1800})
    assert r.status_code == 200 and r.json()["default_markup_bp"] == 1800
    assert admin.patch("/api/v1/settings", json={"default_markup_bp": -1}).status_code == 422
    p = product(admin, category="hardware")
    assert p["category"] == "hardware"
    r = admin.patch(f"/api/v1/products/{p['id']}", json={"category": "license"})
    assert r.json()["category"] == "license"
    assert (
        admin.post(
            "/api/v1/products", json={"name": "x", "unit_price_cents": 1, "category": "bogus"}
        ).status_code
        == 422
    )


def unit_price_for(admin, org, vendor, owner, *, product_id=None, line_markup=None):
    """Deliver one 12,345 c unit and return the resulting charge's unit price."""
    extra = {} if product_id is None else {"product_id": product_id}
    [item] = stock(admin, vendor, markup_bp=line_markup, **extra)
    r = deliver(admin, item, org)
    assert r.status_code == 200, r.text
    return charges(owner)[-1].unit_price_cents, r.json()


def test_markup_resolution_order(admin, vendor, org_ctx, owner):
    org = org_ctx["org"]
    p = product(admin, category="hardware")
    # nothing configured: default 0 bills at cost
    price, item = unit_price_for(admin, org, vendor, owner, product_id=p["id"])
    assert price == 12345 and item["markup_bp"] == 0
    admin.patch("/api/v1/settings", json={"default_markup_bp": 1000})
    assert unit_price_for(admin, org, vendor, owner, product_id=p["id"])[0] == 13580  # +1,234.5
    admin.post(f"{P}/markup-rules", json={"category": "hardware", "markup_bp": 2000})
    assert unit_price_for(admin, org, vendor, owner, product_id=p["id"])[0] == 14814
    # a category rule doesn't apply to an item with no product: the default does
    assert unit_price_for(admin, org, vendor, owner)[0] == 13580
    admin.post(f"{P}/markup-rules", json={"product_id": p["id"], "markup_bp": 1500})
    price, item = unit_price_for(admin, org, vendor, owner, product_id=p["id"])
    assert price == 14197 and item["markup_bp"] == 1500  # 12,345 + round(1,851.75)
    # the line's own markup beats every rule; zero is a real value, not "unset"
    assert (
        unit_price_for(admin, org, vendor, owner, product_id=p["id"], line_markup=100)[0] == 12468
    )
    assert unit_price_for(admin, org, vendor, owner, product_id=p["id"], line_markup=0)[0] == 12345


# ---- receiving --------------------------------------------------------------------------------
def test_partial_then_full_receipt(admin, vendor, owner):
    po = ordered_po(admin, vendor, [line(quantity=5), line(description="Dock", quantity=1)])
    r = receive(admin, po, 0, quantity=2)
    assert r.status_code == 201
    [item] = r.json()
    assert (
        item["quantity"] == 2 and item["status"] == "in_stock" and item["organization_id"] is None
    )
    assert item["description"] == "Laptop" and item["unit_cost_cents"] == 12345
    assert item["received_on"] == biz_today().isoformat()
    url = f"{P}/purchase-orders/{po['id']}"
    got = admin.get(url).json()
    assert got["status"] == "partial" and got["lines"][0]["received_quantity"] == 2
    assert receive(admin, po, 0, quantity=4).status_code == 409  # more than ordered
    assert "more than ordered" in receive(admin, po, 0, quantity=4).json()["detail"]
    assert receive(admin, po, 0, quantity=3).status_code == 201
    assert admin.get(url).json()["status"] == "partial"  # the second line is still open
    assert receive(admin, po, 1, quantity=1).status_code == 201
    got = admin.get(url).json()
    assert got["status"] == "received"
    assert receive(admin, po, 1, quantity=1).status_code == 409  # fully received
    assert receive(admin, po, 0, quantity=0).status_code == 422
    open_po = ordered_po(admin, vendor, [line()])
    r = admin.post(
        f"{P}/purchase-orders/{open_po['id']}/receive", json={"line_id": 9999, "quantity": 1}
    )
    assert r.status_code == 404
    assert "purchase_order.receive" in audit_actions(owner)


def test_cannot_receive_a_draft(admin, vendor):
    po = make_po(admin, vendor, [line()])
    assert receive(admin, po).status_code == 409


def test_serialised_receiving(admin, vendor):
    po = ordered_po(admin, vendor, [line(quantity=3, serialised=True)])
    assert receive(admin, po, quantity=3, serials=["A1", "B2"]).status_code == 409  # count
    assert receive(admin, po, quantity=2).status_code == 409  # serials required
    assert receive(admin, po, quantity=2, serials=["A1", "a1"]).status_code == 422  # repeat
    r = receive(admin, po, quantity=2, serials=[" SN-ab ", "SN-cd"])
    assert r.status_code == 201
    assert sorted((i["serial_number"], i["quantity"]) for i in r.json()) == [
        ("SN-ab", 1),
        ("SN-cd", 1),
    ]
    other = ordered_po(admin, vendor, [line(serialised=True)])
    r = receive(admin, other, serials=["sn-AB"])  # same serial, different case, other PO
    assert r.status_code == 409 and "SN-ab" in r.json()["detail"]
    assert receive(admin, other, serials=["SN-new"]).status_code == 201


def test_serials_on_a_plain_line_are_rejected(admin, vendor):
    po = ordered_po(admin, vendor, [line(quantity=2)])
    r = receive(admin, po, quantity=1, serials=["X1"])
    assert r.status_code == 409 and "not serialised" in r.json()["detail"]


def test_po_for_a_client_reserves_its_stock(admin, vendor, org_ctx, make_org):
    org = org_ctx["org"]
    po = ordered_po(admin, vendor, [line()], organization_id=org)
    [item] = receive(admin, po).json()
    assert item["organization_id"] == org and item["organization_name"] == "Acme Corp"
    other = make_org("Other Co")["id"]
    r = deliver(admin, item, other)
    assert r.status_code == 409 and "reserved" in r.json()["detail"]
    assert deliver(admin, item, org).status_code == 200


# ---- delivery ---------------------------------------------------------------------------------
def test_full_delivery_creates_one_marked_up_charge(admin, vendor, org_ctx, owner):
    admin.post(f"{P}/markup-rules", json={"category": "other", "markup_bp": 1500})
    p = product(admin, category="other", taxable=False)
    [item] = stock(admin, vendor, quantity=3, product_id=p["id"])
    when = (biz_today() - timedelta(days=2)).isoformat()
    r = deliver(admin, item, org_ctx["org"], quantity=3, delivered_on=when)
    assert r.status_code == 200, r.text
    out = r.json()
    assert (out["status"], out["organization_id"], out["delivered_on"]) == (
        "delivered",
        org_ctx["org"],
        when,
    )
    assert out["markup_bp"] == 1500 and out["product_charge_id"] is not None
    [c] = charges(owner)
    assert (c.unit_price_cents, int(c.quantity), c.taxable, c.product_id) == (
        14197,
        3,
        False,
        p["id"],
    )
    assert c.id == out["product_charge_id"] and c.voided_at is None
    assert c.description == "Laptop"
    assert deliver(admin, item, org_ctx["org"]).status_code == 409  # already delivered
    assert {"inventory.deliver", "charge.create"} <= set(audit_actions(owner))


def test_partial_delivery_splits_a_plain_row(admin, vendor, org_ctx, owner):
    [item] = stock(admin, vendor, quantity=5)
    r = deliver(admin, item, org_ctx["org"], quantity=2)
    assert r.status_code == 200
    part = r.json()
    assert part["id"] != item["id"] and part["quantity"] == 2 and part["status"] == "delivered"
    rest = admin.get(f"{P}/inventory/{item['id']}").json()
    assert rest["quantity"] == 3 and rest["status"] == "in_stock"
    assert rest["organization_id"] is None and rest["product_charge_id"] is None
    assert part["purchase_order_line_id"] == rest["purchase_order_line_id"]
    assert [int(c.quantity) for c in charges(owner)] == [2]
    assert deliver(admin, item, org_ctx["org"], quantity=4).status_code == 409  # more than held


def test_delivery_validation(admin, vendor, org_ctx):
    [item] = stock(admin, vendor)
    assert deliver(admin, item, 9999).status_code == 404
    assert deliver(admin, item, org_ctx["org"], quantity=2).status_code == 409
    assert admin.post(f"{P}/inventory/9999/deliver", json={"organization_id": 1}).status_code == 404
    both = deliver(admin, item, org_ctx["org"], asset_id=1, create_asset=True)
    assert both.status_code == 422
    [bulk] = stock(admin, vendor, quantity=2)
    r = deliver(admin, bulk, org_ctx["org"], quantity=2, create_asset=True)
    assert r.status_code == 409  # a multi-unit row can't be one asset


def test_asset_link_same_client_only(admin, vendor, org_ctx, make_org, owner):
    other = make_org("Other Co")["id"]
    ids = {}
    for key, org in (("mine", org_ctx["org"]), ("theirs", other)):
        owner.execute(
            text("INSERT INTO assets (organization_id, kind, name) VALUES (:o, 'other', :n)"),
            {"o": org, "n": key},
        )
        ids[key] = owner.execute(
            text("SELECT id FROM assets WHERE name = :n"), {"n": key}
        ).scalar_one()
    [item] = stock(admin, vendor, serials=["SN-1"])
    r = deliver(admin, item, org_ctx["org"], asset_id=ids["theirs"])
    assert r.status_code == 409
    r = deliver(admin, item, org_ctx["org"], asset_id=ids["mine"])
    assert r.status_code == 200 and r.json()["asset_id"] == ids["mine"]


def test_create_asset_carries_the_serial(admin, vendor, org_ctx, owner):
    [item] = stock(admin, vendor, serials=["SN-9876-XYZ"])
    r = deliver(admin, item, org_ctx["org"], create_asset=True)
    assert r.status_code == 200, r.text
    asset_id = r.json()["asset_id"]
    assert asset_id is not None
    row = owner.execute(
        text("SELECT organization_id, name, serial, serial_norm FROM assets WHERE id = :i"),
        {"i": asset_id},
    ).one()
    assert row == (org_ctx["org"], "Laptop", "SN-9876-XYZ", "SN9876XYZ")
    assert admin.get(f"/api/v1/assets/{asset_id}").status_code == 200
    [c] = charges(owner)
    assert c.description == "Laptop (S/N SN-9876-XYZ)"


def test_non_billable_line_creates_no_charge(admin, vendor, org_ctx, owner):
    [item] = stock(admin, vendor, billable=False)
    r = deliver(admin, item, org_ctx["org"])
    assert r.status_code == 200
    assert r.json()["markup_bp"] is None and r.json()["product_charge_id"] is None
    assert charges(owner) == []
    undone = admin.post(f"{P}/inventory/{item['id']}/undo-delivery")
    assert undone.status_code == 200 and undone.json()["status"] == "in_stock"


def test_consume_is_internal_and_never_billed(admin, vendor, org_ctx, owner):
    [item] = stock(admin, vendor)
    r = admin.post(f"{P}/inventory/{item['id']}/consume")
    assert r.status_code == 200 and r.json()["status"] == "consumed"
    assert admin.post(f"{P}/inventory/{item['id']}/consume").status_code == 409
    assert deliver(admin, item, org_ctx["org"]).status_code == 409
    assert charges(owner) == []
    assert "inventory.consume" in audit_actions(owner)


# ---- undoing a delivery -----------------------------------------------------------------------
def test_undo_before_invoicing_voids_the_charge_and_restores_stock(admin, vendor, org_ctx, owner):
    po = ordered_po(admin, vendor, [line(serialised=True)], organization_id=org_ctx["org"])
    [item] = receive(admin, po, serials=["SN-undo-1"]).json()
    out = deliver(admin, item, org_ctx["org"], create_asset=True).json()
    asset_id = out["asset_id"]
    r = admin.post(f"{P}/inventory/{item['id']}/undo-delivery")
    assert r.status_code == 200, r.text
    back = r.json()
    assert back["status"] == "in_stock" and back["asset_id"] is None
    assert back["product_charge_id"] is None and back["markup_bp"] is None
    assert back["delivered_on"] is None
    assert back["organization_id"] == org_ctx["org"]  # the PO's reservation is restored
    [c] = charges(owner)
    assert c.voided_at is not None
    assert (
        owner.execute(
            text("SELECT count(*) FROM assets WHERE id = :i"), {"i": asset_id}
        ).scalar_one()
        == 1
    )
    assert admin.post(f"{P}/inventory/{item['id']}/undo-delivery").status_code == 409
    # delivering again makes a fresh charge
    assert deliver(admin, item, org_ctx["org"]).status_code == 200
    assert len(charges(owner)) == 2 and charges(owner)[1].voided_at is None
    assert "inventory.undo_delivery" in audit_actions(owner)


def test_undo_after_the_charge_is_invoiced_is_refused(
    admin, biller, vendor, org_ctx, company, owner
):
    [item] = stock(admin, vendor)
    assert deliver(admin, item, org_ctx["org"]).status_code == 200
    run = biller.post("/api/v1/billing-runs", json={"period": biz_today().strftime("%Y-%m")})
    assert run.status_code == 201, run.text
    assert charges(owner)[0].invoice_line_id is not None
    r = admin.post(f"{P}/inventory/{item['id']}/undo-delivery")
    assert r.status_code == 409 and "Already invoiced" in r.json()["detail"]
    assert admin.get(f"{P}/inventory/{item['id']}").json()["status"] == "delivered"


def test_undo_needs_a_delivered_item(admin, vendor):
    [item] = stock(admin, vendor)
    assert admin.post(f"{P}/inventory/{item['id']}/undo-delivery").status_code == 409


# ---- the invoice ------------------------------------------------------------------------------
def test_delivered_item_becomes_one_product_invoice_line(
    admin, biller, vendor, org_ctx, taxed, company
):
    admin.post(f"{P}/markup-rules", json={"category": "hardware", "markup_bp": 1500})
    p = product(admin, category="hardware", taxable=True)
    [item] = stock(admin, vendor, quantity=3, product_id=p["id"])
    assert deliver(admin, item, org_ctx["org"], quantity=3).status_code == 200
    inv = biller.post("/api/v1/invoices", json={"organization_id": org_ctx["org"]}).json()
    inv = biller.get(f"/api/v1/invoices/{inv['id']}").json()
    [ln] = inv["lines"]
    assert ln["kind"] == "product" and ln["unit_price_cents"] == 14197
    assert float(ln["quantity"]) == 3
    assert ln["amount_cents"] == 3 * 14197  # 42,591
    assert ln["tax_cents"] == 3514  # round(42,591 x 8.25%)
    assert (inv["subtotal_cents"], inv["tax_cents"]) == (42591, 3514)


def test_untaxable_line_carries_no_tax(admin, biller, vendor, org_ctx, taxed, company):
    [item] = stock(admin, vendor, taxable=False)
    deliver(admin, item, org_ctx["org"])
    inv = biller.post("/api/v1/invoices", json={"organization_id": org_ctx["org"]}).json()
    [ln] = biller.get(f"/api/v1/invoices/{inv['id']}").json()["lines"]
    assert (ln["amount_cents"], ln["tax_cents"]) == (12345, 0)


# ---- inventory listing ------------------------------------------------------------------------
def test_inventory_filters(admin, vendor, org_ctx):
    p = product(admin)
    [a] = stock(admin, vendor, serials=["ZX-100"], product_id=p["id"])
    [b] = stock(admin, vendor, description="Dock station")
    deliver(admin, a, org_ctx["org"])
    ids = lambda **q: sorted(i["id"] for i in admin.get(f"{P}/inventory", params=q).json())  # noqa: E731
    assert ids() == sorted([a["id"], b["id"]])
    assert ids(status="delivered") == [a["id"]]
    assert ids(status="in_stock") == [b["id"]]
    assert ids(organization_id=org_ctx["org"]) == [a["id"]]
    assert ids(product_id=p["id"]) == [a["id"]]
    assert ids(q="zx-1") == [a["id"]]
    assert ids(q="DOCK") == [b["id"]]
    assert ids(q="nothing") == []
    mine = admin.get(f"{P}/organizations/{org_ctx['org']}/inventory").json()
    assert [i["id"] for i in mine] == [a["id"]] and mine[0]["organization_name"] == "Acme Corp"
