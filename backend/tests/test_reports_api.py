"""Management report routes: JSON and CSV, report:read only; cost rates are admin-only."""

import csv
import io

import pytest

PARAMS = {"from": "2026-03-01", "to": "2026-03-31"}
JSON_ROUTES = ["sla", "utilisation", "aging", "profitability"]
CSV_HEADERS = {
    "sla": "group,tickets,first_response_met",
    "utilisation": "user,capacity_minutes,logged_minutes",
    "aging": "client,current,1-30",
    "profitability": "client,revenue,labour_cost",
}


def routes():
    for name in JSON_ROUTES:
        yield f"/api/reports/{name}"
        yield f"/api/reports/{name}.csv"


@pytest.mark.parametrize("path", list(routes()))
@pytest.mark.parametrize("role", ["billing", "admin"])
def test_report_readers_get_every_report(login, path, role):
    r = login(role).get(path, params=PARAMS)
    assert r.status_code == 200, r.text


@pytest.mark.parametrize("path", list(routes()))
@pytest.mark.parametrize("role", ["tech", "read_only"])
def test_techs_and_read_only_are_refused_every_report(login, path, role):
    assert login(role).get(path, params=PARAMS).status_code == 403


def test_reports_require_login(anon):
    for path in routes():
        assert anon.get(path).status_code == 401


@pytest.mark.parametrize("name", JSON_ROUTES)
def test_csv_content_type_header_and_total_row(biller, name):
    r = biller.get(f"/api/reports/{name}.csv", params=PARAMS)
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment; filename=" in r.headers["content-disposition"]
    assert name in r.headers["content-disposition"]
    rows = list(csv.reader(io.StringIO(r.text)))
    assert ",".join(rows[0]).startswith(CSV_HEADERS[name])
    assert rows[-1][0] == "Total"  # an empty report still has its totals row


def test_csv_downloads_are_audited(admin, biller):
    biller.get("/api/reports/sla.csv", params=PARAMS)
    biller.get("/api/reports/aging.csv")
    hits = admin.get("/api/audit", params={"action": "report.export"}).json()["items"]
    assert sorted(h["detail"]["report"] for h in hits) == ["aging", "sla"]
    assert all("rows" in h["detail"] for h in hits)


def test_sla_csv_group_and_json_shape(biller):
    r = biller.get("/api/reports/sla.csv", params={**PARAMS, "group": "assignee"})
    assert "sla-by-assignee-2026-03-01-2026-03-31.csv" in r.headers["content-disposition"]
    d = biller.get("/api/reports/sla", params={**PARAMS, "group": "organization"}).json()
    assert d["group"] == "organization" and d["range"] == {
        "start": "2026-03-01",
        "end": "2026-03-31",
    }
    assert set(d["totals"]) == {"n", "first_response", "resolution"}
    assert set(d["totals"]["first_response"]) == {
        "met", "breached", "pending", "no_sla", "met_bp", "p50_minutes", "p90_minutes",
    }  # fmt: skip


def test_default_range_and_invalid_range(biller):
    assert biller.get("/api/reports/profitability").status_code == 200
    for name in ("sla", "utilisation", "profitability"):
        bad = biller.get(f"/api/reports/{name}", params={"from": "2026-05-02", "to": "2026-05-01"})
        assert bad.status_code == 409


# ---- cost rates ----
def test_cost_rate_is_admin_only(admin, login, make_user):
    target = make_user("tech", "worker@example.com")["id"]
    assert admin.get(f"/api/users/{target}/cost-rate").json() == {
        "user_id": target,
        "cost_rate_cents": None,
    }
    r = admin.put(f"/api/users/{target}/cost-rate", json={"cost_rate_cents": 9000})
    assert r.status_code == 200 and r.json()["cost_rate_cents"] == 9000
    assert admin.get(f"/api/users/{target}/cost-rate").json()["cost_rate_cents"] == 9000
    for role in ("billing", "tech", "read_only"):
        c = login(role)
        assert c.get(f"/api/users/{target}/cost-rate").status_code == 403
        assert (
            c.put(f"/api/users/{target}/cost-rate", json={"cost_rate_cents": 1}).status_code == 403
        )
    assert admin.get(f"/api/users/{target}/cost-rate").json()["cost_rate_cents"] == 9000


def test_cost_rate_validation_clear_and_audit(admin, make_user):
    target = make_user("tech", "worker@example.com")["id"]
    url = f"/api/users/{target}/cost-rate"
    assert admin.put(url, json={"cost_rate_cents": -1}).status_code == 422
    assert admin.put(url, json={}).status_code == 422
    assert admin.put(url, json={"cost_rate_cents": 0}).json()["cost_rate_cents"] == 0
    admin.put(url, json={"cost_rate_cents": 7500})
    admin.put(url, json={"cost_rate_cents": 7500})  # unchanged: no second audit row
    assert admin.put(url, json={"cost_rate_cents": None}).json()["cost_rate_cents"] is None
    assert admin.get("/api/users/999999/cost-rate").status_code == 404
    assert admin.put("/api/users/999999/cost-rate", json={"cost_rate_cents": 1}).status_code == 404
    hits = admin.get("/api/audit", params={"action": "user.cost_rate"}).json()["items"]
    changes = {(h["detail"]["from"], h["detail"]["to"]) for h in hits}
    assert changes == {(None, 0), (0, 7500), (7500, None)}
    assert len(hits) == 3 and all(h["entity_id"] == target for h in hits)


def test_cost_rate_never_appears_outside_the_admin_endpoints(admin, login, make_user):
    target = make_user("tech", "worker@example.com")["id"]
    admin.put(f"/api/users/{target}/cost-rate", json={"cost_rate_cents": 9000})
    for client in (admin, login("tech"), login("billing")):
        listing = client.get("/api/users")
        assert listing.status_code == 200 and "cost_rate" not in listing.text
        assert "cost_rate" not in client.get("/api/auth/me").text
    patched = admin.patch(f"/api/users/{target}", json={"display_name": "Renamed"})
    assert patched.status_code == 200 and "cost_rate" not in patched.text
