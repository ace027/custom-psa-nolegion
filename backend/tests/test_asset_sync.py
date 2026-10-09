"""The sync: idempotent, non-destructive, de-duplicating, and respectful of manual corrections."""

from datetime import timedelta

from sqlalchemy import text

from tests.conftest import biz_today
from tests.test_integrations import connect
from tests.vendorfakes import HUDU, NINJA, dev, run_sync, vendors  # noqa: F401


def setup_ninja(admin, make_org, vendors, assets, name="Acme Corp"):  # noqa: F811
    org = make_org(name)
    i = connect(admin)
    v = vendors[i["id"]]
    v.clients = {"7": name}
    v.assets = {"7": assets}
    m = admin.post(f"/api/integrations/{i['id']}/clients/refresh").json()[0]
    admin.put(f"/api/integrations/{i['id']}/clients/{m['id']}", json={"organization_id": org["id"]})
    return org, i, v


def assets_of(admin, org, **q):
    r = admin.get(f"/api/organizations/{org['id']}/assets", params=q)
    assert r.status_code == 200, r.text
    return r.json()


def iso(days):
    return (biz_today() + timedelta(days=days)).isoformat()


def test_first_sync_creates_assets_with_derived_warranty_status(admin, make_org, vendors):  # noqa: F811
    org, i, _ = setup_ninja(
        admin,
        make_org,
        vendors,
        [
            dev("1", "PC-OLD", "SER-OLD-0001", end=iso(-5)),
            dev("2", "PC-SOON", "SER-SOON-002", end=iso(20)),
            dev("3", "PC-60", "SER-SIXT-003", end=iso(50)),
            dev("4", "PC-90", "SER-NINE-004", end=iso(80)),
            dev("5", "PC-OK", "SER-GOOD-005", end=iso(400)),
            dev("6", "PC-NONE", "SER-NONE-006"),
        ],
    )
    run = run_sync(i["id"])
    assert run["status"] == "ok" and run["added"] == 6 and run["clients_synced"] == 1
    got = {a["name"]: a["warranty_status"] for a in assets_of(admin, org)}
    assert got == {
        "PC-OLD": "expired",
        "PC-SOON": "expiring_30",
        "PC-60": "expiring_60",
        "PC-90": "expiring_90",
        "PC-OK": "in_warranty",
        "PC-NONE": "unknown",
    }


def test_a_repeat_sync_changes_nothing(admin, make_org, vendors, owner):  # noqa: F811
    org, i, _ = setup_ninja(
        admin, make_org, vendors, [dev("1", end=iso(100)), dev("2", "PC-2", "SER-TWO-0002")]
    )
    run_sync(i["id"])
    before = owner.execute(
        text("SELECT id, name, serial, warranty_end FROM assets ORDER BY id")
    ).all()
    again = run_sync(i["id"])
    assert (again["added"], again["changed"], again["retired"]) == (0, 0, 0)
    assert (
        owner.execute(text("SELECT id, name, serial, warranty_end FROM assets ORDER BY id")).all()
        == before
    )
    assert owner.execute(text("SELECT count(*) FROM asset_sources")).scalar() == 2


def test_a_vendor_change_updates_the_asset_and_is_audited(admin, make_org, vendors, owner):  # noqa: F811
    org, i, v = setup_ninja(admin, make_org, vendors, [dev("1", end=iso(100))])
    run_sync(i["id"])
    v.assets["7"] = [dev("1", end=iso(500))]
    run = run_sync(i["id"])
    assert run["changed"] == 1
    assert assets_of(admin, org)[0]["warranty_end"] == iso(500)
    row = owner.execute(
        text("SELECT before, after FROM audit_log WHERE action='asset.warranty_changed'")
    ).one()
    assert row.before["warranty_end"] == iso(100) and row.after["warranty_end"] == iso(500)


def test_failed_sync_changes_nothing_and_shows_a_clear_error(admin, make_org, vendors):  # noqa: F811
    org, i, v = setup_ninja(admin, make_org, vendors, [dev("1", end=iso(100))])
    run_sync(i["id"])
    v.fail_clients = True
    run = run_sync(i["id"])
    assert run["status"] == "failed" and "down" in run["error"]
    assert [a["name"] for a in assets_of(admin, org)] == ["PC-1"]
    state = admin.get("/api/integrations").json()[0]
    assert state["status"] == "error" and state["last_error"]


def test_a_client_that_fails_is_left_alone_while_others_sync(admin, make_org, vendors, owner):  # noqa: F811
    org_a, i, v = setup_ninja(admin, make_org, vendors, [dev("1")])
    org_b = make_org("Globex")
    v.clients["8"] = "Globex"
    v.assets["8"] = [dev("9", "G-PC", "SER-GLOB-0009")]
    rows = admin.post(f"/api/integrations/{i['id']}/clients/refresh").json()
    gid = next(r["id"] for r in rows if r["external_id"] == "8")
    admin.put(f"/api/integrations/{i['id']}/clients/{gid}", json={"organization_id": org_b["id"]})
    run_sync(i["id"])
    v.fail_assets = {"7"}
    v.assets["7"] = []  # would look like "everything gone" if it were trusted
    v.assets["8"].append(dev("10", "G-PC2", "SER-GLOB-0010"))
    run = run_sync(i["id"])
    assert run["status"] == "partial" and run["clients_failed"] == 1 and run["added"] == 1
    assert len(assets_of(admin, org_a)) == 1 and len(assets_of(admin, org_b)) == 2


def test_vanished_devices_are_retired_after_the_grace_period_not_deleted(
    admin, make_org, vendors, owner
):  # noqa: F811
    org, i, v = setup_ninja(admin, make_org, vendors, [dev("1"), dev("2", "PC-2", "SER-TWO-0002")])
    run_sync(i["id"])
    v.assets["7"] = [dev("1")]
    assert run_sync(i["id"])["retired"] == 0  # just missing, still inside the grace period
    owner.execute(
        text(
            "UPDATE asset_sources SET last_seen_at = now() - interval '40 days' "
            "WHERE external_id = '2'"
        )
    )
    assert run_sync(i["id"])["retired"] == 1
    assert [a["name"] for a in assets_of(admin, org)] == ["PC-1"]
    assert {a["name"] for a in assets_of(admin, org, include_retired=True)} == {"PC-1", "PC-2"}
    assert owner.execute(text("SELECT count(*) FROM assets")).scalar() == 2  # never deleted
    v.assets["7"] = [dev("1"), dev("2", "PC-2", "SER-TWO-0002")]  # it comes back
    run_sync(i["id"])
    assert {a["name"] for a in assets_of(admin, org)} == {"PC-1", "PC-2"}


def test_unmapped_and_ignored_clients_are_never_synced(admin, make_org, vendors, owner):  # noqa: F811
    make_org("Acme Corp")
    i = connect(admin)
    v = vendors[i["id"]]
    v.clients = {"7": "Acme Corp", "8": "Ignored Inc"}
    v.assets = {"7": [dev("1")], "8": [dev("2", "X", "SER-IGNO-0002")]}
    rows = admin.post(f"/api/integrations/{i['id']}/clients/refresh").json()
    ig = next(r for r in rows if r["external_id"] == "8")
    admin.put(f"/api/integrations/{i['id']}/clients/{ig['id']}", json={"ignored": True})
    run = run_sync(i["id"])
    assert (
        run["clients_synced"] == 0
        and owner.execute(text("SELECT count(*) FROM assets")).scalar() == 0
    )


def test_same_serial_in_both_systems_merges_with_two_sources(admin, make_org, vendors, owner):  # noqa: F811
    org, ninja, nv = setup_ninja(
        admin, make_org, vendors, [dev("1", "pc-1", "SN-ABCD-1234", end=iso(100))]
    )
    hudu = connect(admin, HUDU)
    hv = vendors[hudu["id"]]
    hv.clients = {"H1": "Acme Corp"}
    hv.assets = {"H1": [dev("a9", "PC-1 (hudu)", "sn abcd 1234", end=iso(100))]}
    m = admin.post(f"/api/integrations/{hudu['id']}/clients/refresh").json()[0]
    admin.put(
        f"/api/integrations/{hudu['id']}/clients/{m['id']}", json={"organization_id": org["id"]}
    )
    run_sync(ninja["id"])
    run_sync(hudu["id"])
    rows = assets_of(admin, org)
    assert len(rows) == 1 and rows[0]["conflict"] is False
    assert len(admin.get(f"/api/assets/{rows[0]['id']}").json()["sources"]) == 2


def test_disagreeing_warranty_dates_are_flagged_not_silently_resolved(admin, make_org, vendors):  # noqa: F811
    org, ninja, nv = setup_ninja(admin, make_org, vendors, [dev("1", end=iso(100))])
    hudu = connect(admin, HUDU)
    vendors[hudu["id"]].clients = {"H1": "Acme Corp"}
    vendors[hudu["id"]].assets = {"H1": [dev("a9", "PC-1", "SN-ABCD-1234", end=iso(300))]}
    m = admin.post(f"/api/integrations/{hudu['id']}/clients/refresh").json()[0]
    admin.put(
        f"/api/integrations/{hudu['id']}/clients/{m['id']}", json={"organization_id": org["id"]}
    )
    run_sync(ninja["id"])
    run_sync(hudu["id"])
    row = assets_of(admin, org)[0]
    assert row["conflict"] is True
    assert row["warranty_end"] == iso(100)  # NinjaOne owns computers


def test_network_gear_takes_its_values_from_hudu_first(admin, make_org, vendors):  # noqa: F811
    org, ninja, nv = setup_ninja(
        admin, make_org, vendors, [dev("1", "sw-core", "SW-CORE-0001", kind="other", end=iso(100))]
    )
    hudu = connect(admin, HUDU)
    vendors[hudu["id"]].clients = {"H1": "Acme Corp"}
    vendors[hudu["id"]].assets = {
        "H1": [dev("a9", "Core Switch", "SW-CORE-0001", kind="network", end=iso(900))]
    }
    m = admin.post(f"/api/integrations/{hudu['id']}/clients/refresh").json()[0]
    admin.put(
        f"/api/integrations/{hudu['id']}/clients/{m['id']}", json={"organization_id": org["id"]}
    )
    run_sync(ninja["id"])
    run_sync(hudu["id"])
    row = assets_of(admin, org)[0]
    assert row["kind"] == "network" and row["name"] == "Core Switch"
    assert row["warranty_end"] == iso(900)


def test_junk_serials_never_merge_unrelated_devices(admin, make_org, vendors):  # noqa: F811
    org, i, _ = setup_ninja(
        admin,
        make_org,
        vendors,
        [
            dev("1", "A", "To Be Filled By O.E.M."),
            dev("2", "B", "To Be Filled By O.E.M."),
            dev("3", "C", "0"),
            dev("4", "D", "0"),
        ],
    )
    run_sync(i["id"])
    assert len(assets_of(admin, org)) == 4


def test_hostname_fallback_only_when_a_serial_is_missing(admin, make_org, vendors):  # noqa: F811
    org, ninja, _ = setup_ninja(
        admin, make_org, vendors, [dev("1", "FILE-SRV", None, kind="server")]
    )
    hudu = connect(admin, HUDU)
    vendors[hudu["id"]].clients = {"H1": "Acme Corp"}
    vendors[hudu["id"]].assets = {
        "H1": [
            dev(
                "a1", "file-srv", "SRV-FILE-0001", kind="server"
            ),  # no serial on the other side: merge
            dev("a2", "FILE-SRV", "SRV-FILE-0002", kind="server"),  # serial on both and they differ
        ]
    }
    m = admin.post(f"/api/integrations/{hudu['id']}/clients/refresh").json()[0]
    admin.put(
        f"/api/integrations/{hudu['id']}/clients/{m['id']}", json={"organization_id": org["id"]}
    )
    run_sync(ninja["id"])
    run_sync(hudu["id"])
    assert len(assets_of(admin, org)) == 2


def test_same_serial_in_two_clients_stays_two_assets(admin, make_org, vendors):  # noqa: F811
    org_a, i, v = setup_ninja(admin, make_org, vendors, [dev("1")])
    org_b = make_org("Globex")
    v.clients["8"] = "Globex"
    v.assets["8"] = [dev("2")]  # same serial, different client
    rows = admin.post(f"/api/integrations/{i['id']}/clients/refresh").json()
    gid = next(r["id"] for r in rows if r["external_id"] == "8")
    admin.put(f"/api/integrations/{i['id']}/clients/{gid}", json={"organization_id": org_b["id"]})
    run_sync(i["id"])
    assert len(assets_of(admin, org_a)) == 1 and len(assets_of(admin, org_b)) == 1


def test_override_wins_survives_sync_and_can_be_removed(admin, make_org, vendors, owner):  # noqa: F811
    org, i, v = setup_ninja(admin, make_org, vendors, [dev("1", end=iso(-10))])
    run_sync(i["id"])
    a = assets_of(admin, org)[0]
    assert a["warranty_status"] == "expired"
    r = admin.put(
        f"/api/assets/{a['id']}/overrides/warranty_end",
        json={"value": iso(200), "reason": "Extended warranty per invoice 4471"},
    )
    assert r.status_code == 200 and r.json()["warranty_status"] == "in_warranty"
    v.assets["7"] = [dev("1", end=iso(-3))]  # the vendor still has it wrong
    run_sync(i["id"])
    row = assets_of(admin, org)[0]
    assert row["warranty_end"] == iso(200) and row["warranty_overridden"] is True
    assert admin.get(f"/api/assets/{a['id']}").json()["sources"][0]["data"]["warranty_end"] == iso(
        -3
    )
    gone = admin.delete(f"/api/assets/{a['id']}/overrides/warranty_end")
    assert gone.status_code == 200 and gone.json()["warranty_end"] == iso(-3)
    actions = [r[0] for r in owner.execute(text("SELECT action FROM audit_log ORDER BY id"))]
    assert "asset.override_set" in actions and "asset.override_cleared" in actions


def test_override_needs_a_reason_and_a_known_field(admin, make_org, vendors):  # noqa: F811
    org, i, _ = setup_ninja(admin, make_org, vendors, [dev("1")])
    run_sync(i["id"])
    a = assets_of(admin, org)[0]
    url = f"/api/assets/{a['id']}/overrides"
    assert (
        admin.put(f"{url}/warranty_end", json={"value": iso(5), "reason": "  "}).status_code == 409
    )
    assert admin.put(f"{url}/serial", json={"value": iso(5), "reason": "x"}).status_code == 409
    assert admin.delete(f"{url}/warranty_end").status_code == 404
    assert (
        admin.put(
            "/api/assets/999/overrides/warranty_end", json={"value": iso(5), "reason": "x"}
        ).status_code
        == 404
    )


def test_remapping_a_vendor_client_moves_its_devices(admin, make_org, vendors):  # noqa: F811
    org_a, i, v = setup_ninja(admin, make_org, vendors, [dev("1")])
    org_b = make_org("Globex")
    run_sync(i["id"])
    m = admin.get(f"/api/integrations/{i['id']}/clients").json()[0]
    admin.put(
        f"/api/integrations/{i['id']}/clients/{m['id']}", json={"organization_id": org_b["id"]}
    )
    run_sync(i["id"])
    assert len(assets_of(admin, org_b)) == 1


def test_due_logic_respects_interval_and_sync_now(admin, make_org, vendors, owner):  # noqa: F811
    from app import db as dbmod
    from app.asset_sync import due
    from app.deps import Ctx
    from app.scope import Scope

    org, i, _ = setup_ninja(admin, make_org, vendors, [dev("1")])

    def due_ids():
        with dbmod.new_session() as db:
            dbmod.set_org_scope(db, "all")
            return [x.id for x in due(Ctx(db=db, user=None, scope=Scope.all()))]

    assert due_ids() == [i["id"]]  # never synced
    run_sync(i["id"])
    assert due_ids() == []
    admin.post(f"/api/integrations/{i['id']}/sync")
    assert due_ids() == [i["id"]]  # "sync now"
    run_sync(i["id"])
    assert due_ids() == []
    owner.execute(text("UPDATE integrations SET last_sync_at = now() - interval '7 hours'"))
    owner.execute(text("UPDATE sync_runs SET started_at = now() - interval '7 hours'"))
    assert due_ids() == [i["id"]]
    admin.patch(f"/api/integrations/{i['id']}", json={"enabled": False})
    assert due_ids() == []
