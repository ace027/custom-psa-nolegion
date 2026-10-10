"""Assets, the warranty report, and what portal contacts can and cannot see."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import app
from tests.conftest import RouteRecorder
from tests.test_asset_sync import assets_of, iso, setup_ninja
from tests.test_portal import add_contact, link_emails, portal_on, sign_in, token_for  # noqa: F401
from tests.vendorfakes import dev, run_sync, vendors  # noqa: F401


@pytest.fixture
def synced(admin, make_org, vendors):  # noqa: F811
    org, i, v = setup_ninja(
        admin,
        make_org,
        vendors,
        [
            dev("1", "PC-OLD", "SER-OLD-0001", end=iso(-5)),
            dev("2", "PC-SOON", "SER-SOON-002", end=iso(20)),
            dev("3", "PC-OK", "SER-GOOD-005", end=iso(400)),
            dev("4", "PC-NONE", "SER-NONE-006"),
        ],
    )
    run_sync(i["id"])
    return org, i, v


def test_warranty_report_orders_soonest_first_and_counts(admin, synced):
    r = admin.get("/api/reports/warranty").json()
    assert [x["name"] for x in r["rows"]] == ["PC-OLD", "PC-SOON", "PC-OK", "PC-NONE"]
    assert r["total"] == 4 and r["counts"]["expired"] == 1 and r["counts"]["unknown"] == 1


def test_warranty_report_filters(admin, synced):
    org = synced[0]
    assert [
        x["name"] for x in admin.get("/api/reports/warranty?status=expired").json()["rows"]
    ] == ["PC-OLD"]
    soon = admin.get("/api/reports/warranty?within_days=30").json()["rows"]
    assert [x["name"] for x in soon] == ["PC-OLD", "PC-SOON"]
    assert admin.get(f"/api/reports/warranty?organization_id={org['id'] + 99}").json()["total"] == 0
    assert admin.get("/api/reports/warranty?status=bogus").status_code == 409


def test_warranty_report_uses_corrected_dates_and_skips_retired_and_inactive(
    admin, make_org, synced, owner
):
    org = synced[0]
    old = next(a for a in assets_of(admin, org) if a["name"] == "PC-OLD")
    admin.put(
        f"/api/assets/{old['id']}/overrides/warranty_end",
        json={"value": iso(500), "reason": "renewed"},
    )
    r = admin.get("/api/reports/warranty?status=expired").json()
    assert r["total"] == 0
    owner.execute(text("UPDATE assets SET retired_at = now() WHERE name = 'PC-NONE'"))
    assert admin.get("/api/reports/warranty").json()["total"] == 3
    admin.patch(f"/api/organizations/{org['id']}", json={"status": "inactive"})
    assert admin.get("/api/reports/warranty").json()["total"] == 0


def test_warranty_csv_is_audited_and_neutralises_formulas(admin, make_org, vendors, owner):  # noqa: F811
    org, i, _ = setup_ninja(
        admin, make_org, vendors, [dev("1", "=cmd()", "SER-FORM-0001", end=iso(10))]
    )
    run_sync(i["id"])
    r = admin.get("/api/reports/warranty.csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert "'=cmd()" in r.text and "\r\n=cmd()" not in r.text
    assert (
        owner.execute(text("SELECT count(*) FROM audit_log WHERE action='report.export'")).scalar()
        == 1
    )


def test_permissions_for_assets_and_reports(login, synced):
    org = synced[0]
    asset_id = assets_of(login("admin"), org)[0]["id"]
    for role in ("tech", "billing", "read_only"):
        c = login(role)
        assert c.get(f"/api/organizations/{org['id']}/assets").status_code == 200
        assert c.get(f"/api/assets/{asset_id}").status_code == 200
    body = {"value": iso(9), "reason": "x"}
    assert (
        login("tech").put(f"/api/assets/{asset_id}/overrides/warranty_end", json=body).status_code
        == 200
    )
    assert (
        login("read_only")
        .put(f"/api/assets/{asset_id}/overrides/warranty_end", json=body)
        .status_code
        == 403
    )
    assert (
        login("billing").delete(f"/api/assets/{asset_id}/overrides/warranty_end").status_code == 403
    )
    # revenue-adjacent reports follow the existing report permission
    assert login("tech").get("/api/reports/warranty").status_code == 403
    assert login("tech").get("/api/reports/warranty.csv").status_code == 403
    assert login("billing").get("/api/reports/warranty").status_code == 200
    # publishing to the portal is an admin decision
    for role in ("tech", "billing", "read_only"):
        r = login(role).put(
            f"/api/organizations/{org['id']}/assets-sharing", json={"published": True}
        )
        assert r.status_code == 403


def test_unknown_organization_and_asset_are_404(admin):
    assert admin.get("/api/organizations/999/assets").status_code == 404
    assert admin.get("/api/assets/999").status_code == 404
    assert (
        admin.put("/api/organizations/999/assets-sharing", json={"published": True}).status_code
        == 404
    )


def test_assets_are_isolated_by_row_level_security(synced, owner):
    from app.db import new_session, set_org_scope

    org = synced[0]
    other = owner.execute(
        text("INSERT INTO organizations (name) VALUES ('Other') RETURNING id")
    ).scalar()
    with new_session() as db:
        set_org_scope(db, str(other))
        assert db.execute(text("SELECT count(*) FROM assets")).scalar() == 0
        assert db.execute(text("SELECT count(*) FROM asset_sources")).scalar() == 0
        set_org_scope(db, str(org["id"]))
        assert db.execute(text("SELECT count(*) FROM assets")).scalar() == 4


def test_assets_are_never_deletable_by_the_app_role(synced):
    from sqlalchemy.exc import ProgrammingError

    from app.db import new_session, set_org_scope

    with new_session() as db:
        set_org_scope(db, "all")
        with pytest.raises(ProgrammingError):
            db.execute(text("DELETE FROM assets"))


# ---- portal ----
def portal_setup(admin, synced, *, published, flag):
    org = synced[0]
    contact = add_contact(admin, org["id"], "Pat", "pat@acme.com")
    if flag:
        r = admin.patch(f"/api/contacts/{contact['id']}", json={"portal_assets": True})
        assert r.status_code == 200, r.text
    if published:
        assert (
            admin.put(
                f"/api/organizations/{org['id']}/assets-sharing", json={"published": True}
            ).status_code
            == 200
        )
    return org, contact


def test_portal_devices_need_both_publish_and_the_contact_flag(admin, synced, sign_in):  # noqa: F811
    for published, flag in ((False, False), (True, False), (False, True)):
        admin.post("/api/auth/dev-login", json={"email": "admin@example.com"})
        org = synced[0]
        c = None
        # fresh contact each round so state does not leak between rounds
        contact = add_contact(
            admin, org["id"], f"C{published}{flag}", f"c{published}{flag}@acme.com"
        )
        if flag:
            admin.patch(f"/api/contacts/{contact['id']}", json={"portal_assets": True})
        admin.put(f"/api/organizations/{org['id']}/assets-sharing", json={"published": published})
        c = sign_in(f"c{published}{flag}@acme.com")
        assert c.get("/api/portal/assets").status_code == 403
        assert c.get("/api/portal/me").json()["can_see_devices"] is False


def test_portal_devices_for_a_designated_contact_on_a_published_client(
    admin, synced, sign_in, owner
):  # noqa: F811
    portal_setup(admin, synced, published=True, flag=True)
    c = sign_in("pat@acme.com")
    assert c.get("/api/portal/me").json()["can_see_devices"] is True
    body = c.get("/api/portal/assets").json()
    assert body["total"] == 4 and body["counts"]["expired"] == 1
    names = [d["name"] for d in body["devices"]]
    assert set(names) == {"PC-OLD", "PC-SOON", "PC-OK", "PC-NONE"}
    # no serials, vendor ids or internal fields leak to the client
    assert set(body["devices"][0]) == {
        "name",
        "kind",
        "manufacturer",
        "model",
        "warranty_end",
        "warranty_status",
    }


def test_portal_devices_exclude_retired_and_other_clients(admin, make_org, synced, sign_in, owner):  # noqa: F811
    org, _ = portal_setup(admin, synced, published=True, flag=True)
    other = make_org("Globex")
    owner.execute(
        text(
            "INSERT INTO assets (organization_id, kind, name) VALUES (:o, 'computer', 'GLOBEX-SECRET')"
        ),
        {"o": other["id"]},
    )
    owner.execute(text("UPDATE assets SET retired_at = now() WHERE name = 'PC-NONE'"))
    c = sign_in("pat@acme.com")
    names = {d["name"] for d in c.get("/api/portal/assets").json()["devices"]}
    assert "GLOBEX-SECRET" not in names and "PC-NONE" not in names


def test_portal_devices_denial_is_logged_and_withdrawing_stops_access(
    admin, synced, sign_in, owner
):  # noqa: F811
    org, _ = portal_setup(admin, synced, published=True, flag=True)
    c = sign_in("pat@acme.com")
    assert c.get("/api/portal/assets").status_code == 200
    admin.put(f"/api/organizations/{org['id']}/assets-sharing", json={"published": False})
    assert c.get("/api/portal/assets").status_code == 403
    assert (
        owner.execute(text("SELECT count(*) FROM audit_log WHERE action='portal.denied'")).scalar()
        == 1
    )
    assert (
        owner.execute(
            text("SELECT count(*) FROM audit_log WHERE action='asset.sharing_changed'")
        ).scalar()
        == 2
    )


def test_only_an_admin_can_flag_a_contact_for_devices(login, admin, synced):
    org = synced[0]
    contact = add_contact(admin, org["id"], "Pat", "pat@acme.com")
    tech = login("tech")
    r = tech.patch(f"/api/contacts/{contact['id']}", json={"portal_assets": True})
    assert r.status_code == 403
    assert (
        admin.patch(f"/api/contacts/{contact['id']}", json={"portal_assets": True}).status_code
        == 200
    )


def test_unauthenticated_portal_assets_is_refused():
    c = TestClient(RouteRecorder(app), headers={"X-Requested-With": "psa"})
    assert c.get("/api/portal/assets").status_code == 401
