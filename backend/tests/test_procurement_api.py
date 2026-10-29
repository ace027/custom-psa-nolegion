"""Procurement API: every route, permissions per role, 404 / 409 / 422 behaviour, response shapes."""

import pytest

from tests.test_procurement import (  # noqa: F401
    P,
    deliver,
    line,
    make_po,
    ordered_po,
    receive,
    stock,
    tech,
    vendor,
)


@pytest.fixture
def reader(login):
    return login("read_only")


def test_every_route_responds(admin, tech, reader, vendor, org_ctx):
    assert reader.get(f"{P}/vendors").status_code == 200
    assert reader.get(f"{P}/markup-rules").status_code == 200
    assert reader.get(f"{P}/inventory").status_code == 200
    assert reader.get(f"{P}/purchase-orders").status_code == 200
    po = make_po(admin, vendor, [line(serialised=True)], organization_id=org_ctx["org"])
    url = f"{P}/purchase-orders/{po['id']}"
    assert reader.get(url).status_code == 200
    assert admin.patch(url, json={"notes": "n"}).status_code == 200
    assert admin.post(f"{url}/order").status_code == 200
    items = receive(admin, po, serials=["API-1"]).json()
    item = items[0]
    assert reader.get(f"{P}/inventory/{item['id']}").status_code == 200
    assert reader.get(f"{P}/organizations/{org_ctx['org']}/inventory").status_code == 200
    assert admin.post(f"{P}/inventory/{item['id']}/consume").status_code == 200
    again = stock(admin, vendor)[0]
    assert deliver(admin, again, org_ctx["org"]).status_code == 200
    assert admin.post(f"{P}/inventory/{again['id']}/undo-delivery").status_code == 200
    cancel = ordered_po(admin, vendor, [line()])
    assert admin.post(f"{P}/purchase-orders/{cancel['id']}/cancel").status_code == 200


def test_listing_filters_for_purchase_orders(admin, vendor, org_ctx):
    a = make_po(admin, vendor, [line()])
    b = ordered_po(admin, vendor, [line()], organization_id=org_ctx["org"])
    rows = admin.get(f"{P}/purchase-orders").json()
    assert [r["id"] for r in rows] == [b["id"], a["id"]]
    assert [r["id"] for r in admin.get(f"{P}/purchase-orders?status=draft").json()] == [a["id"]]
    mine = admin.get(f"{P}/purchase-orders?organization_id={org_ctx['org']}").json()
    assert [r["id"] for r in mine] == [b["id"]]
    assert len(admin.get(f"{P}/purchase-orders?vendor_id={vendor['id']}").json()) == 2
    assert admin.get(f"{P}/purchase-orders?vendor_id=999").json() == []
    assert admin.get(f"{P}/purchase-orders?status=bogus").status_code == 422


def test_permissions(admin, tech, reader, vendor, org_ctx):
    po = make_po(admin, vendor, [line()])
    rule = admin.post(f"{P}/markup-rules", json={"category": "other", "markup_bp": 100}).json()
    [item] = stock(admin, vendor)
    writes = [
        ("post", f"{P}/vendors", {"name": "Nope"}),
        ("patch", f"{P}/vendors/{vendor['id']}", {"notes": "x"}),
        ("post", f"{P}/purchase-orders", {"vendor_id": vendor["id"]}),
        ("patch", f"{P}/purchase-orders/{po['id']}", {"notes": "x"}),
        ("post", f"{P}/purchase-orders/{po['id']}/lines", line()),
        ("post", f"{P}/purchase-orders/{po['id']}/order", None),
        ("post", f"{P}/purchase-orders/{po['id']}/cancel", None),
        ("post", f"{P}/purchase-orders/{po['id']}/receive", {"line_id": 1, "quantity": 1}),
        ("post", f"{P}/inventory/{item['id']}/deliver", {"organization_id": org_ctx["org"]}),
        ("post", f"{P}/inventory/{item['id']}/undo-delivery", None),
        ("post", f"{P}/inventory/{item['id']}/consume", None),
    ]
    for method, path, body in writes:
        r = getattr(reader, method)(path, **({} if body is None else {"json": body}))
        assert r.status_code == 403, (method, path)
    # techs can work with procurement but not change markup (a billing decision)
    assert tech.post(f"{P}/vendors", json={"name": "Tech vendor"}).status_code == 201
    for method, path, body in (
        ("post", f"{P}/markup-rules", {"category": "license", "markup_bp": 1}),
        ("patch", f"{P}/markup-rules/{rule['id']}", {"markup_bp": 5}),
        ("delete", f"{P}/markup-rules/{rule['id']}", None),
    ):
        r = getattr(tech, method)(path, **({} if body is None else {"json": body}))
        assert r.status_code == 403, (method, path)
    assert admin.get(f"{P}/markup-rules").json()[0]["markup_bp"] == 100


def test_unauthenticated_requests_are_refused(anon):
    assert anon.get(f"{P}/vendors").status_code == 401
    assert anon.get(f"{P}/inventory").status_code == 401


def test_missing_ids_are_404(admin, vendor):
    po = make_po(admin, vendor, [line()])
    missing = [
        ("get", f"{P}/purchase-orders/999"),
        ("patch", f"{P}/purchase-orders/999"),
        ("post", f"{P}/purchase-orders/999/lines"),
        ("patch", f"{P}/purchase-orders/{po['id']}/lines/999"),
        ("delete", f"{P}/purchase-orders/{po['id']}/lines/999"),
        ("post", f"{P}/purchase-orders/999/order"),
        ("post", f"{P}/purchase-orders/999/cancel"),
        ("post", f"{P}/purchase-orders/999/receive"),
        ("get", f"{P}/inventory/999"),
        ("post", f"{P}/inventory/999/deliver"),
        ("post", f"{P}/inventory/999/undo-delivery"),
        ("post", f"{P}/inventory/999/consume"),
        ("get", f"{P}/organizations/999/inventory"),
        ("patch", f"{P}/markup-rules/999"),
        ("delete", f"{P}/markup-rules/999"),
    ]
    bodies = {
        "lines": line(),
        "receive": {"line_id": 1, "quantity": 1},
        "deliver": {"organization_id": 1},
    }
    for method, path in missing:
        body = next((b for k, b in bodies.items() if path.endswith(k)), None)
        if method == "patch":
            body = {"markup_bp": 1} if "markup" in path else {"notes": "x", "quantity": 2}
        kw = {} if body is None else {"json": body}
        r = getattr(admin, method)(path, **kw)
        assert r.status_code == 404, (method, path, r.status_code, r.text)


def test_lifecycle_conflicts_are_409(admin, vendor, org_ctx):
    po = ordered_po(admin, vendor, [line()])
    url = f"{P}/purchase-orders/{po['id']}"
    assert admin.post(f"{url}/order").json()["detail"]
    assert admin.post(f"{url}/lines", json=line()).status_code == 409
    [item] = receive(admin, po).json()
    assert admin.post(f"{url}/cancel").status_code == 409
    assert admin.post(f"{P}/inventory/{item['id']}/undo-delivery").status_code == 409
    assert deliver(admin, item, org_ctx["org"]).status_code == 200
    assert admin.post(f"{P}/inventory/{item['id']}/consume").status_code == 409
    assert deliver(admin, item, org_ctx["org"]).status_code == 409


def test_validation_is_422(admin, vendor):
    assert admin.post(f"{P}/vendors", json={"name": ""}).status_code == 422
    r = admin.post(
        f"{P}/purchase-orders", json={"vendor_id": vendor["id"], "lines": [line(quantity=0)]}
    )
    assert r.status_code == 422
    r = admin.post(
        f"{P}/markup-rules", json={"category": "hardware", "product_id": 1, "markup_bp": 5}
    )
    assert r.status_code == 422
    r = admin.post(f"{P}/markup-rules", json={"category": "hardware", "markup_bp": 100_001})
    assert r.status_code == 422


def test_response_shapes(admin, vendor, org_ctx):
    po = make_po(admin, vendor, [line()], organization_id=org_ctx["org"], vendor_reference="V-1")
    assert po["number"] == f"PO-{po['id']}" and po["vendor_name"] == "Ingram"
    assert po["vendor_reference"] == "V-1" and po["created_by"] == admin.user["id"]
    [ln] = po["lines"]
    assert {"id", "position", "received_quantity", "serialised", "billable", "markup_bp"} <= set(ln)
    admin.post(f"{P}/purchase-orders/{po['id']}/order")
    [item] = receive(admin, po).json()
    assert item["organization_name"] == "Acme Corp" and item["status"] == "in_stock"
    assert {"serial_number", "unit_cost_cents", "asset_id", "product_charge_id"} <= set(item)
    listed = admin.get(f"{P}/inventory").json()
    assert listed[0]["organization_name"] == "Acme Corp"
    fetched = admin.get(f"{P}/purchase-orders/{po['id']}").json()
    assert fetched["lines"][0]["received_quantity"] == 1 and fetched["status"] == "received"
