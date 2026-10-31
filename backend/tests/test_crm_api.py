"""CRM API: every route, permissions per role, validation, and the lead -> client -> quote ->
accepted -> won flow through the existing quote routes."""

from datetime import timedelta

import pytest
from sqlalchemy import text

from app import worker
from tests.conftest import biz_today
from tests.test_quoting import approved, prospect, rates, tech  # noqa: F401


@pytest.fixture
def reader(login):
    return login("read_only")


@pytest.fixture
def stages(admin):
    return {s["name"]: s for s in admin.get("/api/v1/crm/stages").json()}


def lead(client, **kw):
    r = client.post("/api/v1/crm/leads", json={"name": "Pat Prospect", "company": "Widgets", **kw})
    assert r.status_code == 201, r.text
    return r.json()


def new_opp(client, org, **kw):
    r = client.post(
        "/api/v1/crm/opportunities", json={"organization_id": org, "name": "Deal", **kw}
    )
    assert r.status_code == 201, r.text
    return r.json()


# ---- leads ------------------------------------------------------------------------------------
def test_lead_routes(admin, tech):
    made = lead(tech, email="pat@widgets.example", status="contacted")
    assert made["status"] == "contacted" and made["owner_id"] is None
    lid = made["id"]
    patched = admin.patch(
        f"/api/v1/crm/leads/{lid}", json={"notes": "Call back", "owner_id": admin.user["id"]}
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["owner_name"] == "admin user" and patched.json()["notes"] == "Call back"
    lead(admin, name="Other", company="Gadgets")
    assert len(tech.get("/api/v1/crm/leads").json()) == 2
    assert [
        x["id"] for x in tech.get("/api/v1/crm/leads", params={"status": "contacted"}).json()
    ] == [lid]
    assert [x["id"] for x in tech.get("/api/v1/crm/leads", params={"q": "gadget"}).json()] == [
        lid + 1
    ]
    assert len(tech.get("/api/v1/crm/leads", params={"owner_id": admin.user["id"]}).json()) == 1
    assert admin.patch("/api/v1/crm/leads/9999", json={"notes": "x"}).status_code == 404
    assert admin.patch(f"/api/v1/crm/leads/{lid}", json={"status": "converted"}).status_code == 422
    assert admin.post("/api/v1/crm/leads", json={"name": ""}).status_code == 422


def test_convert_route_and_its_conflicts(admin, tech):
    cold = lead(tech)
    r = tech.post(f"/api/v1/crm/leads/{cold['id']}/convert", json={})
    assert r.status_code == 409 and "qualified" in r.json()["detail"]
    ready = lead(tech, name="Qualified Quinn", company="Quinn Co", status="qualified")
    r = tech.post(
        f"/api/v1/crm/leads/{ready['id']}/convert",
        json={"monthly_cents": 120_000, "term_months": 24, "name": "Quinn managed services"},
    )
    assert r.status_code == 201, r.text
    opp = r.json()
    assert (opp["name"], opp["stage_name"], opp["stage_kind"]) == (
        "Quinn managed services",
        "Qualify",
        "open",
    )
    assert opp["organization_name"] == "Quinn Co" and opp["probability_bp"] == 1000
    assert opp["owner_name"] == "tech user" and opp["term_months"] == 24
    org = admin.get(f"/api/v1/organizations/{opp['organization_id']}").json()
    assert org["status"] == "prospect"
    [contact] = admin.get(f"/api/v1/organizations/{org['id']}/contacts").json()
    assert contact["name"] == "Qualified Quinn" and contact["is_primary"]
    assert tech.post(f"/api/v1/crm/leads/{ready['id']}/convert", json={}).status_code == 409
    after = [x for x in tech.get("/api/v1/crm/leads").json() if x["id"] == ready["id"]][0]
    assert after["status"] == "converted" and after["converted_organization_id"] == org["id"]
    assert tech.patch(f"/api/v1/crm/leads/{ready['id']}", json={"notes": "x"}).status_code == 409
    assert tech.post("/api/v1/crm/leads/9999/convert", json={}).status_code == 404


# ---- opportunities ----------------------------------------------------------------------------
def test_opportunity_routes(admin, tech, make_org, stages):
    org = make_org("Deal Client")["id"]
    o = new_opp(tech, org, monthly_cents=50_000, expected_close_date="2026-12-01", kind="upsell")
    assert o["stage_name"] == "Qualify" and o["owner_name"] == "tech user"
    assert o["quote_number"] is None and o["agreement_name"] is None
    oid = o["id"]
    got = admin.get(f"/api/v1/crm/opportunities/{oid}")
    assert got.status_code == 200 and got.json()["organization_name"] == "Deal Client"
    p = admin.patch(
        f"/api/v1/crm/opportunities/{oid}",
        json={"monthly_cents": 75_000, "expected_close_date": None, "name": "Bigger deal"},
    )
    assert p.status_code == 200, p.text
    assert (p.json()["monthly_cents"], p.json()["expected_close_date"]) == (75_000, None)
    p = admin.patch(f"/api/v1/crm/opportunities/{oid}", json={"name": None, "monthly_cents": None})
    assert p.status_code == 200 and p.json()["name"] == "Bigger deal"
    other = new_opp(admin, org, name="Second")
    listed = tech.get("/api/v1/crm/opportunities").json()
    assert {x["id"] for x in listed} == {oid, other["id"]}
    assert [
        x["id"] for x in tech.get("/api/v1/crm/opportunities", params={"kind": "upsell"}).json()
    ] == [oid]
    q = {"organization_id": org, "owner_id": admin.user["id"], "stage_id": stages["Qualify"]["id"]}
    assert [x["id"] for x in tech.get("/api/v1/crm/opportunities", params=q).json()] == [
        other["id"]
    ]
    assert admin.get("/api/v1/crm/opportunities/9999").status_code == 404
    assert admin.patch("/api/v1/crm/opportunities/9999", json={"name": "x"}).status_code == 404
    bad = admin.post(
        "/api/v1/crm/opportunities", json={"organization_id": org, "name": "x", "monthly_cents": -1}
    )
    assert bad.status_code == 422
    bad = admin.post(
        "/api/v1/crm/opportunities", json={"organization_id": org, "name": "x", "term_months": 0}
    )
    assert bad.status_code == 422
    assert (
        admin.post(
            "/api/v1/crm/opportunities", json={"organization_id": 9999, "name": "x"}
        ).status_code
        == 404
    )
    won = stages["Won"]["id"]
    assert (
        admin.post(
            "/api/v1/crm/opportunities", json={"organization_id": org, "name": "x", "stage_id": won}
        ).status_code
        == 409
    )


def test_stage_move_route(tech, make_org, stages):
    org = make_org("Mover")["id"]
    o = new_opp(tech, org)
    url = f"/api/v1/crm/opportunities/{o['id']}/stage"
    moved = tech.post(url, json={"stage_id": stages["Proposal"]["id"]})
    assert moved.status_code == 200 and moved.json()["stage_name"] == "Proposal"
    assert moved.json()["probability_bp"] == 5000
    lost = tech.post(url, json={"stage_id": stages["Lost"]["id"]})
    assert lost.status_code == 409 and "lost reason" in lost.json()["detail"]
    lost = tech.post(url, json={"stage_id": stages["Lost"]["id"], "lost_reason": "Too pricey"})
    assert lost.json()["lost_reason"] == "Too pricey" and lost.json()["closed_at"]
    reopened = tech.post(url, json={"stage_id": stages["Negotiation"]["id"]}).json()
    assert reopened["closed_at"] is None and reopened["lost_reason"] is None
    assert tech.post(url, json={"stage_id": 9999}).status_code == 404
    assert (
        tech.post("/api/v1/crm/opportunities/9999/stage", json={"stage_id": 1}).status_code == 404
    )


# ---- stages -----------------------------------------------------------------------------------
def test_stage_routes_need_config_manage(admin, tech, reader, stages):
    assert list(stages) == ["Qualify", "Site survey", "Proposal", "Negotiation", "Won", "Lost"]
    assert tech.get("/api/v1/crm/stages").status_code == 200
    body = {"name": "Contract review", "position": 45, "probability_bp": 9000, "kind": "open"}
    assert tech.post("/api/v1/crm/stages", json=body).status_code == 403
    assert (
        tech.patch(f"/api/v1/crm/stages/{stages['Qualify']['id']}", json={"name": "x"}).status_code
        == 403
    )
    made = admin.post("/api/v1/crm/stages", json=body)
    assert made.status_code == 201 and made.json()["active"] is True
    assert admin.post("/api/v1/crm/stages", json=body).status_code == 409
    sid = made.json()["id"]
    edited = admin.patch(f"/api/v1/crm/stages/{sid}", json={"probability_bp": 8000, "position": 46})
    assert edited.json()["probability_bp"] == 8000
    assert (
        admin.patch(f"/api/v1/crm/stages/{sid}", json={"active": False}).json()["active"] is False
    )
    won, lost = stages["Won"]["id"], stages["Lost"]["id"]
    assert admin.patch(f"/api/v1/crm/stages/{won}", json={"active": False}).status_code == 409
    assert admin.patch(f"/api/v1/crm/stages/{lost}", json={"active": False}).status_code == 409
    assert admin.patch("/api/v1/crm/stages/9999", json={"name": "x"}).status_code == 404
    bad = {**body, "name": "Z", "probability_bp": 10001}
    assert admin.post("/api/v1/crm/stages", json=bad).status_code == 422


# ---- forecast ---------------------------------------------------------------------------------
def test_forecast_route(admin, reader, make_org, stages):
    empty = reader.get("/api/v1/crm/forecast")
    assert empty.status_code == 200
    assert empty.json()["total"]["count"] == 0 and len(empty.json()["buckets"]) == 15
    org = make_org("Forecast Client")["id"]
    soon = (biz_today() + timedelta(days=3)).isoformat()
    new_opp(admin, org, monthly_cents=333, expected_close_date=soon)
    admin.patch(f"/api/v1/crm/stages/{stages['Qualify']['id']}", json={"probability_bp": 5000})
    f = reader.get("/api/v1/crm/forecast").json()
    assert f["total"]["count"] == 1
    assert f["total"]["monthly_cents"] == 333 and f["total"]["weighted_monthly_cents"] == 167
    assert f["total"]["contract_value_cents"] == 333 * 12
    no_date = new_opp(admin, org, monthly_cents=100)
    by = {b["key"]: b for b in reader.get("/api/v1/crm/forecast").json()["buckets"]}
    assert by["no_date"]["count"] == 1 and no_date["id"]


# ---- permissions ------------------------------------------------------------------------------
def test_read_only_can_read_but_not_write(admin, reader, anon, make_org, stages):
    org = make_org("Readable")["id"]
    ld, o = lead(admin), new_opp(admin, org)
    for path in (
        "/api/v1/crm/leads",
        "/api/v1/crm/opportunities",
        f"/api/v1/crm/opportunities/{o['id']}",
        "/api/v1/crm/forecast",
        "/api/v1/crm/stages",
        "/api/v1/crm/renewals",
    ):
        assert reader.get(path).status_code == 200, path
    writes = [
        ("post", "/api/v1/crm/leads", {"name": "x"}),
        ("patch", f"/api/v1/crm/leads/{ld['id']}", {"notes": "x"}),
        ("post", f"/api/v1/crm/leads/{ld['id']}/convert", {}),
        ("post", "/api/v1/crm/opportunities", {"organization_id": org, "name": "x"}),
        ("patch", f"/api/v1/crm/opportunities/{o['id']}", {"name": "x"}),
        (
            "post",
            f"/api/v1/crm/opportunities/{o['id']}/stage",
            {"stage_id": stages["Proposal"]["id"]},
        ),
        ("post", f"/api/v1/crm/opportunities/{o['id']}/quote", {"quote_id": 1}),
        ("post", "/api/v1/crm/renewals/1/dismiss", {}),
        ("post", "/api/v1/crm/stages", {"name": "x", "position": 1, "probability_bp": 1}),
    ]
    for method, path, body in writes:
        assert getattr(reader, method)(path, json=body).status_code == 403, path
    assert anon.get("/api/v1/crm/leads").status_code == 401


# ---- renewals ---------------------------------------------------------------------------------
def test_renewal_routes_and_the_worker_job(admin, reader, owner, make_org):
    org = make_org("Renew Co")["id"]
    end = biz_today() + timedelta(days=20)
    owner.execute(
        text(
            "INSERT INTO agreements (organization_id, name, type, unit_price_cents, start_date, "
            "end_date) VALUES (:o, 'Gold plan', 'flat', 99900, '2025-01-01', :e)"
        ),
        {"o": org, "e": end},
    )
    assert admin.get("/api/v1/crm/renewals").json() == []
    worker.billing_jobs()
    rows = reader.get("/api/v1/crm/renewals").json()
    assert [(r["lead_days"], r["status"]) for r in rows] == [(90, "open"), (30, "open")]
    assert rows[0]["agreement_name"] == "Gold plan" and rows[0]["organization_name"] == "Renew Co"
    assert rows[0]["due_on"] == end.isoformat() and rows[0]["opportunity_id"]
    [renewal] = admin.get("/api/v1/crm/opportunities", params={"kind": "renewal"}).json()
    assert renewal["monthly_cents"] == 99_900 and renewal["agreement_name"] == "Gold plan"
    worker.billing_jobs()  # idempotent
    assert len(admin.get("/api/v1/crm/renewals").json()) == 2
    done = admin.post(f"/api/v1/crm/renewals/{rows[0]['id']}/dismiss")
    assert done.status_code == 200 and done.json()["status"] == "dismissed"
    assert admin.post(f"/api/v1/crm/renewals/{rows[0]['id']}/dismiss").status_code == 409
    assert admin.post("/api/v1/crm/renewals/9999/dismiss").status_code == 404
    assert [
        r["id"] for r in admin.get("/api/v1/crm/renewals", params={"status": "open"}).json()
    ] == [rows[1]["id"]]
    assert admin.get("/api/v1/crm/renewals", params={"status": "bogus"}).status_code == 422


def test_renewal_settings_are_validated(admin):
    s = admin.get("/api/v1/settings").json()
    assert s["renewal_reminder_days"] == [90, 30] and s["renewal_email"] is None
    ok = admin.patch(
        "/api/v1/settings",
        json={"renewal_reminder_days": [30, 60, 14], "renewal_email": "a@msp.example"},
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["renewal_reminder_days"] == [60, 30, 14]
    assert ok.json()["renewal_email"] == "a@msp.example"
    for bad in ([], [0], [366], [30, 30], [1, 2, 3, 4, 5, 6]):
        assert (
            admin.patch("/api/v1/settings", json={"renewal_reminder_days": bad}).status_code == 422
        )
    assert admin.patch("/api/v1/settings", json={"renewal_email": "nope"}).status_code == 422
    cleared = admin.patch("/api/v1/settings", json={"renewal_email": ""})
    assert cleared.json()["renewal_email"] is None
    assert cleared.json()["renewal_reminder_days"] == [60, 30, 14]


# ---- lead -> client -> quote -> accepted -> won ---------------------------------------------
def test_convert_link_quote_accept_wins_the_opportunity(admin, tech, rates, stages):  # noqa: F811
    ready = lead(
        tech, name="Nina New", company="Flow Co", email="nina@flow.example", status="qualified"
    )
    opp = tech.post(
        f"/api/v1/crm/leads/{ready['id']}/convert", json={"monthly_cents": 100_000}
    ).json()
    org = opp["organization_id"]
    q = approved(tech, org)
    link = f"/api/v1/crm/opportunities/{opp['id']}/quote"
    assert tech.post(link, json={"quote_id": 9999}).status_code == 409
    linked = tech.post(link, json={"quote_id": q["id"]})
    assert linked.status_code == 200, linked.text
    assert linked.json()["quote_number"] == f"Q-{q['id']}"
    elsewhere = admin.post("/api/v1/organizations", json={"name": "Elsewhere"}).json()["id"]
    other_opp = new_opp(admin, elsewhere)
    assert (
        admin.post(
            f"/api/v1/crm/opportunities/{other_opp['id']}/quote", json={"quote_id": q["id"]}
        ).status_code
        == 409
    )
    tech.post(f"/api/v1/quotes/{q['id']}/send", json={})
    still = admin.get(f"/api/v1/crm/opportunities/{opp['id']}").json()
    assert still["stage_kind"] == "open"
    accepted = admin.post(f"/api/v1/quotes/{q['id']}/accept", json={})
    assert accepted.status_code == 200, accepted.text
    agreement = accepted.json()["resulting_agreement_id"]
    won = admin.get(f"/api/v1/crm/opportunities/{opp['id']}").json()
    assert (won["stage_name"], won["stage_kind"]) == ("Won", "won")
    assert won["closed_at"] and won["agreement_id"] == agreement
    assert won["agreement_name"] == f"Managed services (quote Q-{q['id']})"
    assert admin.get(f"/api/v1/organizations/{org}").json()["status"] == "active"
    f = admin.get("/api/v1/crm/forecast").json()
    assert f["won_this_month"]["count"] == 1 and f["total"]["count"] == 1  # the unrelated open one
    closed_link = tech.post(link, json={"quote_id": q["id"]})
    assert closed_link.status_code == 409
    assert (
        admin.get("/api/v1/crm/opportunities", params={"open_only": True}).json()[0]["id"]
        == other_opp["id"]
    )


def test_declining_a_linked_quote_leaves_the_opportunity_open(admin, tech, rates, prospect):  # noqa: F811
    opp = new_opp(tech, prospect)
    q = approved(tech, prospect)
    tech.post(f"/api/v1/crm/opportunities/{opp['id']}/quote", json={"quote_id": q["id"]})
    tech.post(f"/api/v1/quotes/{q['id']}/send", json={})
    assert admin.post(f"/api/v1/quotes/{q['id']}/decline", json={}).status_code == 200
    assert admin.get(f"/api/v1/crm/opportunities/{opp['id']}").json()["stage_kind"] == "open"


def test_a_null_lead_status_is_ignored_not_a_server_error(admin):
    made = lead(admin, status="contacted")
    r = admin.patch(f"/api/v1/crm/leads/{made['id']}", json={"status": None, "notes": "kept"})
    assert r.status_code == 200, r.text
    assert (r.json()["status"], r.json()["notes"]) == ("contacted", "kept")


def test_revising_a_linked_quote_moves_the_opportunity_and_accepting_wins_it(
    admin,
    tech,
    rates,
    prospect,  # noqa: F811
):
    opp = new_opp(tech, prospect)
    q = approved(tech, prospect)
    link = f"/api/v1/crm/opportunities/{opp['id']}/quote"
    assert tech.post(link, json={"quote_id": q["id"]}).status_code == 200
    n = tech.post(f"/api/v1/quotes/{q['id']}/revise").json()
    assert admin.get(f"/api/v1/crm/opportunities/{opp['id']}").json()["quote_id"] == n["id"]
    submitted = tech.post(f"/api/v1/quotes/{n['id']}/submit").json()
    assert submitted["status"] == "approved"
    assert tech.post(f"/api/v1/quotes/{n['id']}/send", json={}).status_code == 200
    assert admin.post(f"/api/v1/quotes/{n['id']}/accept", json={}).status_code == 200
    won = admin.get(f"/api/v1/crm/opportunities/{opp['id']}").json()
    assert won["stage_kind"] == "won" and won["quote_id"] == n["id"]
