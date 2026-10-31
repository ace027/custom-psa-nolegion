import pytest

from tests.test_payments import final_invoice, pay

ROLES = ["admin", "tech", "billing", "read_only"]
ALLOWED = {"read": set(ROLES), "write": {"admin", "billing"}, "finalize": {"admin", "billing"}}

CALLS = [
    ("GET", "/api/v1/payments", None, "read"),
    (
        "POST",
        "/api/v1/payments",
        {"organization_id": 1, "amount_cents": 100, "method": "cash"},
        "write",
    ),
    ("GET", "/api/v1/payments/1", None, "read"),
    ("POST", "/api/v1/payments/1/apply", {"invoice_id": 1, "amount_cents": 1}, "write"),
    ("POST", "/api/v1/payments/1/void", {"reason": "because"}, "finalize"),
    ("POST", "/api/v1/payment-applications/1/void", {"reason": "because"}, "finalize"),
    ("POST", "/api/v1/invoices/1/write-off", {"reason": "because"}, "finalize"),
    ("POST", "/api/v1/write-offs/1/void", {"reason": "because"}, "finalize"),
    ("GET", "/api/v1/receivables", None, "read"),
]


@pytest.mark.parametrize("role", ROLES)
def test_payment_role_matrix(role, login):
    client = login(role)
    for method, path, body, need in CALLS:
        r = client.request(method, path, json=body)
        if role in ALLOWED[need]:
            assert r.status_code not in (401, 403), (role, method, path, r.status_code, r.text)
        else:
            assert r.status_code == 403, (role, method, path, r.status_code)


def test_unauthenticated_payment_requests_get_401(anon):
    for method, path, body, _ in CALLS:
        assert anon.request(method, path, json=body).status_code == 401, (method, path)


def test_techs_can_see_balances_but_not_change_them(login, biller, org_ctx, company):
    inv = final_invoice(biller, org_ctx["org"], 1000)
    tech = login("tech")
    assert tech.get(f"/api/v1/invoices/{inv['id']}").json()["balance_cents"] == 1000
    assert tech.get("/api/v1/receivables").status_code == 200
    assert pay(tech, org_ctx["org"], 100).status_code == 403


def count(admin):
    return admin.get("/api/v1/audit", params={"limit": 1}).json()["total"]


def test_every_payment_write_is_audited(admin, biller, org_ctx, company):
    org = org_ctx["org"]
    a, b, c = (final_invoice(biller, org, 5000) for _ in range(3))
    p1 = pay(biller, org, 9000).json()
    p2 = pay(biller, org, 1000, [{"invoice_id": a["id"], "amount_cents": 1000}]).json()
    wo = biller.post(
        f"/api/v1/invoices/{c['id']}/write-off",
        json={"amount_cents": 100, "reason": "small balance"},
    ).json()
    steps = [
        (
            "POST",
            "/api/v1/payments",
            {"organization_id": org, "amount_cents": 500, "method": "ach", "reference": "ACH-9"},
        ),
        (
            "POST",
            f"/api/v1/payments/{p1['id']}/apply",
            {"invoice_id": b["id"], "amount_cents": 500},
        ),
        (
            "POST",
            f"/api/v1/payment-applications/{p2['applications'][0]['id']}/void",
            {"reason": "wrong invoice"},
        ),
        ("POST", f"/api/v1/payments/{p1['id']}/void", {"reason": "bounced check"}),
        ("POST", f"/api/v1/invoices/{b['id']}/write-off", {"reason": "uncollectible"}),
        ("POST", f"/api/v1/write-offs/{wo['id']}/void", {"reason": "collected after all"}),
    ]
    for method, path, body in steps:
        before = count(admin)
        r = biller.request(method, path, json=body)
        assert r.status_code < 400, (method, path, r.text)
        assert count(admin) > before, f"{method} {path} wrote no audit row"
    actions = {
        x["action"] for x in admin.get("/api/v1/audit", params={"limit": 200}).json()["items"]
    }
    assert {
        "payment.create",
        "payment.apply",
        "payment.unapply",
        "payment.void",
        "invoice.write_off",
        "invoice.write_off_void",
    } <= actions


def test_audit_rows_capture_who_what_and_why(admin, biller, org_ctx, company):
    inv = final_invoice(biller, org_ctx["org"], 5000)
    p = pay(biller, org_ctx["org"], 5000, [{"invoice_id": inv["id"], "amount_cents": 5000}]).json()
    biller.post(f"/api/v1/payments/{p['id']}/void", json={"reason": "NSF"})
    row = admin.get("/api/v1/audit", params={"action": "payment.void"}).json()["items"][0]
    assert row["actor_id"] == biller.user["id"] and row["organization_id"] == org_ctx["org"]
    assert row["before"]["status"] == "active" and row["after"]["status"] == "void"
    assert row["detail"] == {"reason": "NSF", "unapplied_invoices": [inv["id"]]}
