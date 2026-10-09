"""Block-hour / retainer agreements: schema, validation and API (docs/BILLING.md)."""
import pytest
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from alembic import command


def block(client, org, **kw):
    body = {
        "organization_id": org,
        "name": "Retainer",
        "type": "block",
        "unit_price_cents": 100000,
        "block_minutes": 600,
        "start_date": "2026-01-01",
        **kw,
    }
    return client.post("/api/agreements", json=body)


def test_create_block_round_trips_fields(biller, org_ctx):
    r = block(biller, org_ctx["org"], quantity=7, taxable=True)
    assert r.status_code == 201, r.text
    a = r.json()
    assert a["type"] == "block" and a["block_minutes"] == 600
    assert a["quantity"] == 1  # forced, like flat
    assert a["unit_price_cents"] == 100000 and a["monthly_amount_cents"] == 100000
    got = biller.get(f"/api/agreements/{a['id']}").json()
    assert got == a
    listed = biller.get("/api/agreements", params={"organization_id": org_ctx["org"]}).json()
    assert [x["block_minutes"] for x in listed] == [600]
    # other types report no included minutes
    flat = biller.post(
        "/api/agreements",
        json={"organization_id": org_ctx["org"], "name": "Flat", "type": "flat",
              "unit_price_cents": 500, "start_date": "2026-01-01"},
    ).json()
    assert flat["block_minutes"] is None


@pytest.mark.parametrize(
    "kw",
    [
        {"block_minutes": None},
        {"block_minutes": 0},
        {"block_minutes": -15},
        {"block_minutes": 610},  # not a multiple of the default 15-minute increment
        {"block_minutes": 44_640 + 15},  # above a month of round-the-clock hours
    ],
)
def test_invalid_block_minutes_are_422(biller, org_ctx, kw):
    r = block(biller, org_ctx["org"], **kw)
    assert r.status_code == 422, r.text
    assert biller.get("/api/agreements").json() == []


def test_block_minutes_follow_a_non_default_increment(admin, biller, org_ctx):
    assert admin.patch("/api/settings", json={"billing_increment_minutes": 30}).status_code == 200
    r = block(biller, org_ctx["org"], block_minutes=615)  # multiple of 15, not of 30
    assert r.status_code == 422 and "30 minutes" in r.json()["detail"]
    assert block(biller, org_ctx["org"], block_minutes=630).status_code == 201


def test_block_minutes_on_other_types_are_422(biller, org_ctx):
    for t in ("flat", "per_user", "per_device"):
        r = block(biller, org_ctx["org"], type=t)
        assert r.status_code == 422, (t, r.text)
    flat = block(biller, org_ctx["org"], type="flat", block_minutes=None).json()
    r = biller.patch(f"/api/agreements/{flat['id']}", json={"block_minutes": 600})
    assert r.status_code == 422


def test_type_change_flat_to_block_and_back(biller, org_ctx):
    flat = block(biller, org_ctx["org"], type="flat", block_minutes=None).json()
    # becoming a block needs included minutes
    assert biller.patch(f"/api/agreements/{flat['id']}", json={"type": "block"}).status_code == 422
    r = biller.patch(f"/api/agreements/{flat['id']}", json={"type": "block", "block_minutes": 300})
    assert r.status_code == 200 and r.json()["block_minutes"] == 300 and r.json()["type"] == "block"
    # a block cannot drop its minutes while it stays a block
    assert (
        biller.patch(f"/api/agreements/{flat['id']}", json={"block_minutes": None}).status_code
        == 422
    )
    assert biller.patch(f"/api/agreements/{flat['id']}", json={"block_minutes": 0}).status_code == 422
    # explicit minutes on a non-block type are refused
    r = biller.patch(f"/api/agreements/{flat['id']}", json={"type": "flat", "block_minutes": 300})
    assert r.status_code == 422
    # leaving the block type drops the included minutes
    r = biller.patch(f"/api/agreements/{flat['id']}", json={"type": "flat"})
    assert r.status_code == 200 and r.json()["block_minutes"] is None
    assert biller.get(f"/api/agreements/{flat['id']}").json()["type"] == "flat"
    # per_user -> block forces quantity 1 and logs it
    pu = block(biller, org_ctx["org"], type="per_user", quantity=5, block_minutes=None,
               start_date="2030-01-01").json()
    r = biller.patch(f"/api/agreements/{pu['id']}", json={"type": "block", "block_minutes": 60})
    assert r.status_code == 200 and r.json()["quantity"] == 1
    log = biller.get(f"/api/agreements/{pu['id']}/quantity-log").json()
    assert [x["new_quantity"] for x in log] == [1, 5]


def test_one_block_per_client_for_overlapping_dates(biller, org_ctx, make_org):
    org = org_ctx["org"]
    first = block(biller, org, start_date="2026-01-01", end_date="2026-06-30").json()
    assert block(biller, org, start_date="2026-06-30").status_code == 409  # shares one day
    assert block(biller, org, start_date="2025-01-01", end_date=None).status_code == 409
    assert block(biller, org, start_date="2025-06-01", end_date="2026-01-01").status_code == 409
    later = block(biller, org, start_date="2026-07-01")  # open-ended, after the first one
    assert later.status_code == 201, later.text
    # an open-ended block blocks every later start
    assert block(biller, org, start_date="2031-01-01", end_date="2031-12-31").status_code == 409
    earlier = block(biller, org, start_date="2025-01-01", end_date="2025-12-31")
    assert earlier.status_code == 201
    # other types and other clients are unaffected
    assert block(biller, org, type="flat", block_minutes=None).status_code == 201
    other = make_org("Other Co")["id"]
    assert block(biller, other).status_code == 201
    # the 409 says why
    r = block(biller, org, start_date="2026-03-01", end_date="2026-03-31")
    assert r.status_code == 409 and "block agreement" in r.json()["detail"]
    assert first["id"] != later.json()["id"]


def test_update_into_overlap_is_409(biller, org_ctx):
    org = org_ctx["org"]
    a = block(biller, org, start_date="2026-01-01", end_date="2026-03-31").json()
    b = block(biller, org, start_date="2026-04-01", end_date="2026-06-30").json()
    r = biller.patch(f"/api/agreements/{a['id']}", json={"end_date": "2026-04-15"})
    assert r.status_code == 409
    r = biller.patch(f"/api/agreements/{a['id']}", json={"end_date": None})  # open-ended
    assert r.status_code == 409
    assert biller.get(f"/api/agreements/{a['id']}").json()["end_date"] == "2026-03-31"
    # editing itself never conflicts with itself
    r = biller.patch(f"/api/agreements/{a['id']}", json={"end_date": "2026-03-30", "name": "Q1"})
    assert r.status_code == 200 and r.json()["name"] == "Q1"
    # a flat agreement for the same dates turning into a block conflicts
    f = block(biller, org, type="flat", block_minutes=None, start_date="2026-05-01").json()
    r = biller.patch(f"/api/agreements/{f['id']}", json={"type": "block", "block_minutes": 60})
    assert r.status_code == 409
    assert biller.get(f"/api/agreements/{f['id']}").json()["type"] == "flat"
    assert biller.get(f"/api/agreements/{b['id']}").json()["block_minutes"] == 600


def test_work_type_block_covered_round_trip_and_audit(admin, biller):
    rows = {w["name"]: w for w in biller.get("/api/billing/work-types").json()}
    remote = rows["Remote"]
    assert remote["block_covered"] is True  # covered by default
    r = biller.patch(f"/api/billing/work-types/{remote['id']}", json={"block_covered": False})
    assert r.status_code == 200 and r.json()["block_covered"] is False
    # other fields are untouched, and omitting block_covered leaves it alone
    r = biller.patch(f"/api/billing/work-types/{remote['id']}", json={"rate_cents": 15000})
    assert r.json()["block_covered"] is False and r.json()["rate_cents"] == 15000
    rows = {w["name"]: w for w in biller.get("/api/billing/work-types").json()}
    assert rows["Remote"]["block_covered"] is False and rows["Onsite"]["block_covered"] is True
    items = admin.get(
        "/api/audit", params={"action": "work_type.billing_update"}
    ).json()["items"]
    changed = [
        x for x in items
        if (x.get("before") or {}).get("block_covered") is True
        and (x.get("after") or {}).get("block_covered") is False
    ]
    assert len(changed) == 1


def test_permissions(login, org_ctx):
    rows = {w["name"]: w for w in login("admin").get("/api/billing/work-types").json()}
    for role in ("read_only", "tech"):
        c = login(role)
        assert block(c, org_ctx["org"]).status_code == 403
        assert (
            c.patch(
                f"/api/billing/work-types/{rows['Remote']['id']}", json={"block_covered": False}
            ).status_code
            == 403
        )
    a = block(login("admin"), org_ctx["org"]).json()
    assert login("tech").patch(f"/api/agreements/{a['id']}", json={"block_minutes": 300}
                               ).status_code == 403


def test_database_guards(owner, biller, org_ctx):
    a = block(biller, org_ctx["org"]).json()
    with pytest.raises(IntegrityError):
        owner.execute(text("UPDATE agreements SET block_minutes = NULL WHERE id = :i"),
                      {"i": a["id"]})
    with pytest.raises(IntegrityError):
        owner.execute(text("UPDATE agreements SET type = 'flat' WHERE id = :i"), {"i": a["id"]})
    with pytest.raises(IntegrityError):
        owner.execute(text("UPDATE agreements SET block_minutes = 0 WHERE id = :i"),
                      {"i": a["id"]})


def test_time_entry_block_minutes_covered_guard(owner, make_ticket, wt, log):
    t = make_ticket()
    e = log(t["id"], wt["Remote"], 50)  # 60 billable at the 15-minute increment
    row = owner.execute(
        text("SELECT minutes_billable, block_minutes_covered FROM time_entries WHERE id = :i"),
        {"i": e["id"]},
    ).one()
    assert tuple(row) == (60, 0)
    owner.execute(text("UPDATE time_entries SET block_minutes_covered = 60 WHERE id = :i"),
                  {"i": e["id"]})
    for bad in (61, -1):
        with pytest.raises(IntegrityError):
            owner.execute(
                text("UPDATE time_entries SET block_minutes_covered = :v WHERE id = :i"),
                {"v": bad, "i": e["id"]},
            )


def test_downgrade_refuses_while_block_agreements_exist(owner, biller, org_ctx):
    block(biller, org_ctx["org"])
    with pytest.raises(RuntimeError, match="block agreement"):
        command.downgrade(Config("alembic.ini"), "0022")
    head = owner.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    assert head == "0023"
    assert owner.execute(text("SELECT count(*) FROM agreements WHERE type = 'block'")
                         ).scalar_one() == 1
