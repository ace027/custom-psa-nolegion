"""Every billing endpoint x every role, plus proof that every billing write is audited."""

import pytest

ROLES = ["admin", "tech", "billing", "read_only"]
ALLOWED = {
    "read": set(ROLES),
    "write": {"admin", "billing"},
    "finalize": {"admin", "billing"},
    "charge": {"admin", "tech", "billing"},
}

CALLS = [
    ("GET", "/api/billing/work-types", None, "read"),
    ("PATCH", "/api/billing/work-types/1", {"rate_cents": 100}, "write"),
    ("GET", "/api/organizations/1/billing", None, "read"),
    ("PATCH", "/api/organizations/1/billing", {"tax_rate_bp": 1}, "write"),
    ("PUT", "/api/organizations/1/billing/rates/1", {"rate_cents": 1}, "write"),
    ("DELETE", "/api/organizations/1/billing/rates/1", None, "write"),
    ("GET", "/api/products", None, "read"),
    ("POST", "/api/products", {"name": "P", "unit_price_cents": 1}, "write"),
    ("PATCH", "/api/products/1", {"name": "P2"}, "write"),
    ("POST", "/api/products/1/archive", None, "write"),
    ("POST", "/api/products/1/unarchive", None, "write"),
    ("GET", "/api/agreements", None, "read"),
    (
        "POST",
        "/api/agreements",
        {
            "organization_id": 1,
            "name": "A",
            "type": "flat",
            "unit_price_cents": 1,
            "start_date": "2026-01-01",
        },
        "write",
    ),
    ("GET", "/api/agreements/1", None, "read"),
    ("PATCH", "/api/agreements/1", {"name": "A2"}, "write"),
    ("GET", "/api/agreements/1/quantity-log", None, "read"),
    ("GET", "/api/product-charges", None, "read"),
    (
        "POST",
        "/api/product-charges",
        {"organization_id": 1, "description": "x", "unit_price_cents": 1},
        "charge",
    ),
    ("POST", "/api/product-charges/1/void", None, "charge"),
    ("GET", "/api/invoices", None, "read"),
    ("POST", "/api/invoices", {"organization_id": 1}, "write"),
    ("GET", "/api/invoices/1", None, "read"),
    ("PATCH", "/api/invoices/1", {"memo": "m"}, "write"),
    ("POST", "/api/invoices/1/add-unbilled", None, "write"),
    ("POST", "/api/invoices/1/lines", {"description": "x", "unit_price_cents": 1}, "write"),
    ("PATCH", "/api/invoice-lines/1", {"description": "x"}, "write"),
    ("DELETE", "/api/invoice-lines/1", None, "write"),
    ("POST", "/api/invoices/1/finalize", None, "finalize"),
    ("POST", "/api/invoices/1/void", {"reason": "because"}, "finalize"),
    ("GET", "/api/invoices/1/pdf", None, "read"),
    ("GET", "/api/billing-runs", None, "read"),
    ("POST", "/api/billing-runs", {"period": "2026-01"}, "write"),
    ("GET", "/api/billing-runs/1", None, "read"),
    ("POST", "/api/billing-runs/1/review", None, "finalize"),
    ("POST", "/api/billing-runs/1/finalize", None, "finalize"),
    ("POST", "/api/billing-runs/1/cancel", None, "finalize"),
]


@pytest.mark.parametrize("role", ROLES)
def test_billing_role_matrix(role, login):
    client = login(role)
    for method, path, body, need in CALLS:
        r = client.request(method, path, json=body)
        if role in ALLOWED[need]:
            assert r.status_code not in (401, 403), (role, method, path, r.status_code, r.text)
        else:
            assert r.status_code == 403, (role, method, path, r.status_code)


def test_unauthenticated_billing_requests_get_401(anon):
    for method, path, body, _ in CALLS:
        assert anon.request(method, path, json=body).status_code == 401, (method, path)


def test_denied_billing_attempts_are_audited(admin, login):
    login("read_only").post("/api/billing-runs/1/finalize")
    denied = admin.get("/api/audit", params={"action": "auth.denied"}).json()["items"]
    assert denied and denied[0]["detail"]["permission"] == "billing:finalize"


# ---- audit: every billing write leaves a row ----
def count(admin):
    return admin.get("/api/audit", params={"limit": 1}).json()["total"]


def test_every_billing_write_is_audited(admin, biller, org_ctx, wt, company, make_ticket, log):
    org = org_ctx["org"]
    t = make_ticket()
    log(t["id"], wt["Remote"], 30)
    prod = biller.post("/api/products", json={"name": "P", "unit_price_cents": 100}).json()
    ag = biller.post(
        "/api/agreements",
        json={
            "organization_id": org,
            "name": "A",
            "type": "per_user",
            "unit_price_cents": 100,
            "quantity": 2,
            "start_date": "2020-01-01",
        },
    ).json()
    charge = biller.post(
        "/api/product-charges",
        json={"organization_id": org, "description": "c", "unit_price_cents": 5},
    ).json()
    inv = biller.post("/api/invoices", json={"organization_id": org}).json()
    line = biller.post(
        f"/api/invoices/{inv['id']}/lines", json={"description": "m", "unit_price_cents": 10}
    ).json()
    # created AFTER the draft above pulled in existing charges, so this one is still un-invoiced
    voidable = biller.post(
        "/api/product-charges",
        json={"organization_id": org, "description": "v", "unit_price_cents": 5},
    ).json()
    inv2 = biller.post(
        "/api/invoices", json={"organization_id": org, "include_unbilled": False}
    ).json()
    biller.post(
        f"/api/invoices/{inv2['id']}/lines", json={"description": "n", "unit_price_cents": 10}
    )
    writes = [
        ("PATCH", f"/api/billing/work-types/{wt['Remote']}", {"rate_cents": 16000}),
        ("PATCH", f"/api/organizations/{org}/billing", {"payment_terms_days": 10}),
        ("PUT", f"/api/organizations/{org}/billing/rates/{wt['Remote']}", {"rate_cents": 1}),
        ("DELETE", f"/api/organizations/{org}/billing/rates/{wt['Remote']}", None),
        ("POST", "/api/products", {"name": "P9", "unit_price_cents": 1}),
        ("PATCH", f"/api/products/{prod['id']}", {"name": "P10"}),
        ("POST", f"/api/products/{prod['id']}/archive", None),
        ("POST", f"/api/products/{prod['id']}/unarchive", None),
        (
            "POST",
            "/api/agreements",
            {
                "organization_id": org,
                "name": "B",
                "type": "flat",
                "unit_price_cents": 1,
                "start_date": "2020-01-01",
            },
        ),
        ("PATCH", f"/api/agreements/{ag['id']}", {"quantity": 3, "reason": "hire"}),
        (
            "POST",
            "/api/product-charges",
            {"organization_id": org, "description": "d", "unit_price_cents": 1},
        ),
        ("POST", f"/api/product-charges/{voidable['id']}/void", None),
        ("POST", "/api/invoices", {"organization_id": org}),
        ("PATCH", f"/api/invoices/{inv['id']}", {"memo": "m"}),
        ("POST", f"/api/invoices/{inv['id']}/add-unbilled", None),
        ("POST", f"/api/invoices/{inv['id']}/lines", {"description": "z", "unit_price_cents": 1}),
        ("PATCH", f"/api/invoice-lines/{line['id']}", {"description": "edited"}),
        ("DELETE", f"/api/invoice-lines/{line['id']}", None),
        ("POST", f"/api/invoices/{inv2['id']}/finalize", None),
        ("POST", f"/api/invoices/{inv2['id']}/void", {"reason": "test"}),
        ("POST", "/api/billing-runs", {"period": "2099-01"}),  # rejected: nothing written
    ]
    for method, path, body in writes:
        before = count(admin)
        r = biller.request(method, path, json=body)
        if path.endswith("2099-01") or "2099" in str(body):
            assert r.status_code == 422 or r.status_code == 409
            continue
        assert r.status_code < 400, (method, path, r.text)
        assert count(admin) > before, f"{method} {path} wrote no audit row"
    assert charge["id"]


def test_run_lifecycle_is_audited(admin, biller, org_ctx, company):
    from tests.test_billing_runs import agreement, period

    agreement(biller, org_ctx["org"])
    run = biller.post("/api/billing-runs", json={"period": period()}).json()
    biller.post(f"/api/billing-runs/{run['id']}/review")
    biller.post(f"/api/billing-runs/{run['id']}/finalize")
    actions = [a["action"] for a in admin.get("/api/audit", params={"limit": 200}).json()["items"]]
    for expected in (
        "billing_run.create",
        "billing_run.review",
        "billing_run.finalize",
        "invoice.finalize",
        "agreement.create",
    ):
        assert expected in actions, expected
    run2 = biller.post("/api/billing-runs", json={"period": period(1)}).json()
    biller.post(f"/api/billing-runs/{run2['id']}/cancel")
    actions = [a["action"] for a in admin.get("/api/audit", params={"limit": 200}).json()["items"]]
    assert "billing_run.cancel" in actions and "invoice.void" in actions
