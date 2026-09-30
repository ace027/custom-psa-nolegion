import pytest

from tests.conftest import biz_today


# ---- work type rates / org billing settings ----
def test_work_type_rates_default_to_unset_and_are_editable(admin, biller):
    rows = {w["name"]: w for w in biller.get("/api/billing/work-types").json()}
    assert rows["Remote"]["rate_cents"] is None and rows["Remote"]["taxable"] is False
    r = biller.patch(
        f"/api/billing/work-types/{rows['Remote']['id']}",
        json={"rate_cents": 12500, "taxable": True},
    )
    assert r.status_code == 200 and r.json()["rate_cents"] == 12500 and r.json()["taxable"]
    assert (
        admin.patch(
            f"/api/billing/work-types/{rows['Remote']['id']}", json={"rate_cents": None}
        ).json()["rate_cents"]
        is None
    )
    assert biller.patch("/api/billing/work-types/999", json={"rate_cents": 1}).status_code == 404
    assert (
        biller.patch(
            f"/api/billing/work-types/{rows['Remote']['id']}", json={"rate_cents": -5}
        ).status_code
        == 422
    )


def test_org_billing_settings_and_rate_overrides(admin, biller, org_ctx, wt):
    org = org_ctx["org"]
    b = biller.get(f"/api/organizations/{org}/billing").json()
    assert b == {"payment_terms_days": 30, "tax_rate_bp": 0, "rates": []}
    r = biller.patch(
        f"/api/organizations/{org}/billing", json={"payment_terms_days": 15, "tax_rate_bp": 825}
    )
    assert r.status_code == 200 and r.json()["payment_terms_days"] == 15
    assert r.json()["tax_rate_bp"] == 825
    for bad in ({"tax_rate_bp": 10001}, {"payment_terms_days": -1}, {"payment_terms_days": 366}):
        assert biller.patch(f"/api/organizations/{org}/billing", json=bad).status_code == 422
    put = biller.put(
        f"/api/organizations/{org}/billing/rates/{wt['Remote']}", json={"rate_cents": 9900}
    )
    assert put.status_code == 200 and put.json() == {
        "work_type_id": wt["Remote"],
        "rate_cents": 9900,
    }
    biller.put(f"/api/organizations/{org}/billing/rates/{wt['Remote']}", json={"rate_cents": 9500})
    assert biller.get(f"/api/organizations/{org}/billing").json()["rates"] == [
        {"work_type_id": wt["Remote"], "rate_cents": 9500}
    ]
    assert (
        biller.delete(f"/api/organizations/{org}/billing/rates/{wt['Remote']}").status_code == 204
    )
    assert (
        biller.delete(f"/api/organizations/{org}/billing/rates/{wt['Remote']}").status_code == 404
    )
    assert (
        biller.put("/api/organizations/999/billing/rates/1", json={"rate_cents": 1}).status_code
        == 404
    )
    assert (
        biller.put(
            f"/api/organizations/{org}/billing/rates/999", json={"rate_cents": 1}
        ).status_code
        == 404
    )
    assert biller.get("/api/organizations/999/billing").status_code == 404
    assert (
        biller.patch("/api/organizations/999/billing", json={"tax_rate_bp": 1}).status_code == 404
    )
    actions = {
        a["action"] for a in admin.get("/api/audit", params={"action": "org"}).json()["items"]
    }
    assert {"organization.billing_update", "org_rate.set", "org_rate.delete"} <= actions


def test_only_billing_roles_can_change_billing_settings(login, org_ctx):
    org = org_ctx["org"]
    for role in ("tech", "read_only"):
        c = login(role)
        assert c.get(f"/api/organizations/{org}/billing").status_code == 200
        assert (
            c.patch(f"/api/organizations/{org}/billing", json={"tax_rate_bp": 1}).status_code == 403
        )
        assert c.patch("/api/billing/work-types/1", json={"rate_cents": 1}).status_code == 403


# ---- products ----
def test_product_catalog(admin, biller):
    r = biller.post(
        "/api/products",
        json={
            "sku": "LAP-14",
            "name": "Laptop 14in",
            "unit_price_cents": 89900,
            "cost_cents": 70000,
        },
    )
    assert r.status_code == 201 and r.json()["taxable"] is True
    pid = r.json()["id"]
    assert (
        biller.post(
            "/api/products", json={"sku": "lap-14", "name": "Dup", "unit_price_cents": 1}
        ).status_code
        == 409
    )
    assert (
        biller.patch(f"/api/products/{pid}", json={"unit_price_cents": 91900}).json()[
            "unit_price_cents"
        ]
        == 91900
    )
    assert biller.post(f"/api/products/{pid}/archive").json()["archived_at"]
    assert biller.get("/api/products").json() == []
    assert len(biller.get("/api/products", params={"include_archived": True}).json()) == 1
    assert (
        biller.post(
            "/api/products", json={"sku": "LAP-14", "name": "Reuse", "unit_price_cents": 1}
        ).status_code
        == 201
    )
    assert biller.post(f"/api/products/{pid}/unarchive").status_code == 409  # SKU taken again
    assert biller.patch("/api/products/999", json={"name": "x"}).status_code == 404
    assert biller.post("/api/products/999/archive").status_code == 404
    assert biller.post("/api/products/999/unarchive").status_code == 404
    assert (
        biller.post("/api/products", json={"name": "x", "unit_price_cents": -1}).status_code == 422
    )
    assert (
        biller.post("/api/products", json={"name": "No sku", "unit_price_cents": 5}).status_code
        == 201
    )  # SKU is optional, and blank SKUs never collide
    assert (
        biller.post("/api/products", json={"name": "No sku 2", "unit_price_cents": 5}).status_code
        == 201
    )


# ---- agreements ----
def agreement(client, org, **kw):
    body = {
        "organization_id": org,
        "name": "Managed Services",
        "type": "per_user",
        "unit_price_cents": 1200,
        "quantity": 25,
        "start_date": "2026-01-01",
        **kw,
    }
    return client.post("/api/agreements", json=body)


def test_agreement_lifecycle_and_quantity_log(admin, biller, org_ctx):
    r = agreement(biller, org_ctx["org"])
    assert r.status_code == 201, r.text
    a = r.json()
    assert a["monthly_amount_cents"] == 30000 and a["organization_name"] == "Acme Corp"
    r = biller.patch(f"/api/agreements/{a['id']}", json={"quantity": 27, "reason": "2 new hires"})
    assert r.status_code == 200 and r.json()["monthly_amount_cents"] == 32400
    biller.patch(f"/api/agreements/{a['id']}", json={"unit_price_cents": 1300})  # no qty change
    log = biller.get(f"/api/agreements/{a['id']}/quantity-log").json()
    assert [(x["old_quantity"], x["new_quantity"], x["reason"]) for x in log] == [
        (25, 27, "2 new hires"),
        (None, 25, "Agreement created"),
    ]
    assert biller.get(f"/api/agreements/{a['id']}").json()["quantity"] == 27
    assert (
        len(biller.get("/api/agreements", params={"organization_id": org_ctx["org"]}).json()) == 1
    )
    ended = biller.patch(f"/api/agreements/{a['id']}", json={"end_date": "2026-06-30"}).json()
    assert ended["end_date"] == "2026-06-30"
    assert biller.get("/api/agreements", params={"active_on": "2026-07-15"}).json() == []
    assert len(biller.get("/api/agreements", params={"active_on": "2026-06-30"}).json()) == 1
    cleared = biller.patch(f"/api/agreements/{a['id']}", json={"end_date": None}).json()
    assert cleared["end_date"] is None
    actions = [
        x["action"]
        for x in admin.get("/api/audit", params={"action": "agreement."}).json()["items"]
    ]
    assert actions.count("agreement.update") == 4 and "agreement.create" in actions


def test_agreement_rules(biller, org_ctx):
    org = org_ctx["org"]
    flat = agreement(biller, org, type="flat", quantity=5, unit_price_cents=250000).json()
    assert flat["quantity"] == 1 and flat["monthly_amount_cents"] == 250000  # flat is always 1
    assert (
        biller.patch(f"/api/agreements/{flat['id']}", json={"quantity": 9}).json()["quantity"] == 1
    )
    assert agreement(biller, org, end_date="2025-12-31").status_code == 409
    assert agreement(biller, 999).status_code == 404
    assert agreement(biller, org, type="hourly").status_code == 422
    assert agreement(biller, org, quantity=-1).status_code == 422
    assert agreement(biller, org, unit_price_cents=-1).status_code == 422
    assert (
        biller.patch(f"/api/agreements/{flat['id']}", json={"end_date": "2025-01-01"}).status_code
        == 409
    )
    per_dev = agreement(biller, org, type="per_device", quantity=10).json()
    switched = biller.patch(f"/api/agreements/{per_dev['id']}", json={"type": "flat"}).json()
    assert switched["quantity"] == 1
    assert [
        x["new_quantity"]
        for x in biller.get(f"/api/agreements/{per_dev['id']}/quantity-log").json()
    ] == [1, 10]
    assert biller.get("/api/agreements/999").status_code == 404
    assert biller.patch("/api/agreements/999", json={"name": "x"}).status_code == 404
    assert biller.get("/api/agreements/999/quantity-log").status_code == 404


# ---- one-off product charges ----
def product(biller, **kw):
    return biller.post(
        "/api/products",
        json={
            "sku": "SW-1",
            "name": "Antivirus seat",
            "unit_price_cents": 3500,
            "taxable": True,
            **kw,
        },
    ).json()


def test_charge_defaults_from_product_and_price_is_a_snapshot(login, biller, org_ctx):
    p = product(biller)
    tech = login("tech")  # techs may sell parts
    r = tech.post(
        "/api/product-charges",
        json={"organization_id": org_ctx["org"], "product_id": p["id"], "quantity": "3"},
    )
    assert r.status_code == 201, r.text
    c = r.json()
    assert (c["description"], c["unit_price_cents"], c["taxable"]) == ("Antivirus seat", 3500, True)
    assert c["quantity"] == "3.0000" and c["charged_on"] == biz_today().isoformat()
    biller.patch(f"/api/products/{p['id']}", json={"unit_price_cents": 9999})
    assert (
        tech.get("/api/product-charges", params={"organization_id": org_ctx["org"]}).json()[0][
            "unit_price_cents"
        ]
        == 3500
    )  # unchanged


def test_charge_overrides_freeform_and_validation(biller, org_ctx, make_ticket, make_org):
    org = org_ctx["org"]
    p = product(biller)
    r = biller.post(
        "/api/product-charges",
        json={
            "organization_id": org,
            "product_id": p["id"],
            "description": "Custom seat",
            "unit_price_cents": 2000,
            "taxable": False,
            "charged_on": "2026-09-01",
        },
    )
    assert r.json()["description"] == "Custom seat" and r.json()["unit_price_cents"] == 2000
    assert r.json()["taxable"] is False and r.json()["charged_on"] == "2026-09-01"
    free = biller.post(
        "/api/product-charges",
        json={"organization_id": org, "description": "Cable", "unit_price_cents": 900},
    )
    assert free.status_code == 201 and free.json()["taxable"] is False
    assert biller.post("/api/product-charges", json={"organization_id": org}).status_code == 409
    assert (
        biller.post(
            "/api/product-charges", json={"organization_id": org, "description": "x"}
        ).status_code
        == 409
    )
    assert (
        biller.post(
            "/api/product-charges",
            json={"organization_id": 999, "description": "x", "unit_price_cents": 1},
        ).status_code
        == 404
    )
    assert (
        biller.post(
            "/api/product-charges", json={"organization_id": org, "product_id": 999}
        ).status_code
        == 409
    )
    assert (
        biller.post(
            "/api/product-charges",
            json={"organization_id": org, "description": "x", "unit_price_cents": 1, "quantity": 0},
        ).status_code
        == 422
    )
    t = make_ticket()
    ok = biller.post(
        "/api/product-charges",
        json={
            "organization_id": org,
            "ticket_id": t["id"],
            "description": "x",
            "unit_price_cents": 1,
        },
    )
    assert ok.status_code == 201 and ok.json()["ticket_id"] == t["id"]
    other = make_org("Other")
    assert (
        biller.post(
            "/api/product-charges",
            json={
                "organization_id": other["id"],
                "ticket_id": t["id"],
                "description": "x",
                "unit_price_cents": 1,
            },
        ).status_code
        == 409
    )
    assert len(biller.get("/api/product-charges", params={"ticket_id": t["id"]}).json()) == 1
    biller.post(f"/api/product-charges/{ok.json()['id']}/void")
    assert len(biller.get("/api/product-charges", params={"unbilled_only": True}).json()) == 2


def test_void_charge_rules(biller, org_ctx):
    c = biller.post(
        "/api/product-charges",
        json={"organization_id": org_ctx["org"], "description": "x", "unit_price_cents": 1},
    ).json()
    assert biller.post(f"/api/product-charges/{c['id']}/void").json()["voided_at"]
    assert biller.post(f"/api/product-charges/{c['id']}/void").status_code == 409
    assert biller.post("/api/product-charges/999/void").status_code == 404


@pytest.mark.parametrize("role,expected", [("read_only", 403), ("tech", 201), ("billing", 201)])
def test_who_may_create_charges(login, org_ctx, role, expected):
    r = login(role).post(
        "/api/product-charges",
        json={"organization_id": org_ctx["org"], "description": "x", "unit_price_cents": 1},
    )
    assert r.status_code == expected
