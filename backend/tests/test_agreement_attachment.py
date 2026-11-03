"""Agreement on tickets and time entries, and the all-inclusive / rollover settings (phase 17)."""

from datetime import timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from tests.conftest import biz_today


def agreement(client, org, type="block", **kw):
    body = {
        "organization_id": org,
        "name": f"{type} plan",
        "type": type,
        "unit_price_cents": 100000,
        "start_date": (biz_today() - timedelta(days=60)).isoformat(),
        **({"block_minutes": 600} if type == "block" else {}),
        **kw,
    }
    r = client.post("/api/v1/agreements", json=body)
    assert r.status_code == 201, r.text
    return r.json()


# ---- defaulting on ticket create ------------------------------------------------------------
def test_single_block_agreement_is_the_default(biller, org_ctx, make_ticket):
    a = agreement(biller, org_ctx["org"])
    assert make_ticket()["agreement_id"] == a["id"]


def test_single_all_inclusive_flat_is_the_default(biller, org_ctx, make_ticket):
    a = agreement(biller, org_ctx["org"], "flat", all_inclusive=True)
    agreement(biller, org_ctx["org"], "per_user", quantity=5)  # not a candidate
    assert make_ticket()["agreement_id"] == a["id"]


def test_no_candidate_means_no_agreement(biller, org_ctx, make_ticket):
    assert make_ticket()["agreement_id"] is None
    agreement(biller, org_ctx["org"], "flat")  # not all-inclusive
    agreement(biller, org_ctx["org"], "per_user", quantity=5)
    assert make_ticket()["agreement_id"] is None


def test_two_candidates_mean_no_agreement(biller, org_ctx, make_ticket):
    agreement(biller, org_ctx["org"])
    agreement(biller, org_ctx["org"], "flat", all_inclusive=True)
    assert make_ticket()["agreement_id"] is None


def test_ended_or_future_agreements_are_not_candidates(biller, org_ctx, make_ticket):
    today = biz_today()
    agreement(biller, org_ctx["org"], end_date=(today - timedelta(days=1)).isoformat())
    agreement(
        biller,
        org_ctx["org"],
        "flat",
        all_inclusive=True,
        start_date=(today + timedelta(days=1)).isoformat(),
    )
    assert make_ticket()["agreement_id"] is None


# ---- overrides --------------------------------------------------------------------------------
def test_ticket_create_and_patch_override(admin, biller, org_ctx, make_ticket):
    block = agreement(biller, org_ctx["org"])
    flat = agreement(biller, org_ctx["org"], "flat")
    assert make_ticket(agreement_id=None)["agreement_id"] is None  # explicit null wins
    t = make_ticket(agreement_id=flat["id"])
    assert t["agreement_id"] == flat["id"]
    r = admin.patch(f"/api/v1/tickets/{t['id']}", json={"agreement_id": block["id"]})
    assert r.status_code == 200 and r.json()["agreement_id"] == block["id"]
    assert admin.get(f"/api/v1/tickets/{t['id']}").json()["agreement_id"] == block["id"]
    r = admin.patch(f"/api/v1/tickets/{t['id']}", json={"subject": "Still the same agreement"})
    assert r.json()["agreement_id"] == block["id"]
    r = admin.patch(f"/api/v1/tickets/{t['id']}", json={"agreement_id": None})
    assert r.status_code == 200 and r.json()["agreement_id"] is None


def test_other_org_agreement_is_422(admin, biller, org_ctx, make_org, make_ticket, wt):
    other = agreement(biller, make_org("Other Co")["id"])
    r = admin.post(
        "/api/v1/tickets",
        json={"organization_id": org_ctx["org"], "subject": "x", "agreement_id": other["id"]},
    )
    assert r.status_code == 422, r.text
    t = make_ticket()
    assert (
        admin.patch(f"/api/v1/tickets/{t['id']}", json={"agreement_id": other["id"]}).status_code
        == 422
    )
    body = {"work_type_id": wt["Remote"], "minutes": 30, "agreement_id": other["id"]}
    assert admin.post(f"/api/v1/tickets/{t['id']}/time", json=body).status_code == 422
    e = admin.post(
        f"/api/v1/tickets/{t['id']}/time", json={"work_type_id": wt["Remote"], "minutes": 30}
    ).json()
    r = admin.patch(f"/api/v1/time-entries/{e['id']}", json={"agreement_id": other["id"]})
    assert r.status_code == 422, r.text
    assert (
        admin.patch(f"/api/v1/time-entries/{e['id']}", json={"agreement_id": 999999}).status_code
        == 422
    )


def test_time_inherits_ticket_agreement_and_can_be_overridden(
    admin, biller, org_ctx, make_ticket, wt, log
):
    block = agreement(biller, org_ctx["org"])
    flat = agreement(biller, org_ctx["org"], "flat")
    t = make_ticket()
    first = log(t["id"], wt["Remote"], 30)
    assert first["agreement_id"] == block["id"]
    assert log(t["id"], wt["Remote"], 30, agreement_id=flat["id"])["agreement_id"] == flat["id"]
    assert log(t["id"], wt["Remote"], 30, agreement_id=None)["agreement_id"] is None
    # changing the ticket's agreement applies to new time only
    admin.patch(f"/api/v1/tickets/{t['id']}", json={"agreement_id": flat["id"]})
    assert log(t["id"], wt["Remote"], 30)["agreement_id"] == flat["id"]
    entries = {e["id"]: e for e in admin.get(f"/api/v1/tickets/{t['id']}/time").json()}
    assert entries[first["id"]]["agreement_id"] == block["id"]
    r = admin.patch(f"/api/v1/time-entries/{first['id']}", json={"agreement_id": flat["id"]})
    assert r.status_code == 200 and r.json()["agreement_id"] == flat["id"]
    r = admin.patch(f"/api/v1/time-entries/{first['id']}", json={"agreement_id": None})
    assert r.status_code == 200 and r.json()["agreement_id"] is None
    assert r.json()["minutes_actual"] == 30  # nothing else changed


def test_billed_entry_agreement_change_is_409(owner, admin, biller, org_ctx, make_ticket, wt, log):
    flat = agreement(biller, org_ctx["org"], "flat")
    t = make_ticket()
    covered = log(t["id"], wt["Remote"], 60)
    owner.execute(
        text("UPDATE time_entries SET block_minutes_covered = 30 WHERE id = :i"),
        {"i": covered["id"]},
    )
    r = admin.patch(f"/api/v1/time-entries/{covered['id']}", json={"agreement_id": flat["id"]})
    assert r.status_code == 409, r.text

    invoiced = log(t["id"], wt["Remote"], 60)
    r = biller.post("/api/v1/billing-runs", json={"period": biz_today().strftime("%Y-%m")})
    assert r.status_code == 201, r.text
    line = owner.execute(
        text("SELECT invoice_line_id FROM time_entries WHERE id = :i"), {"i": invoiced["id"]}
    ).scalar_one()
    assert line is not None
    r = admin.patch(f"/api/v1/time-entries/{invoiced['id']}", json={"agreement_id": flat["id"]})
    assert r.status_code == 409, r.text
    agreements = owner.execute(
        text("SELECT agreement_id FROM time_entries WHERE id IN (:a, :b)"),
        {"a": covered["id"], "b": invoiced["id"]},
    ).scalars()
    assert set(agreements) == {None}


def test_changes_are_audited(admin, biller, org_ctx, make_ticket, wt, log):
    a = agreement(biller, org_ctx["org"], "flat")
    t = make_ticket()
    admin.patch(f"/api/v1/tickets/{t['id']}", json={"agreement_id": a["id"]})
    e = log(t["id"], wt["Remote"], 30, agreement_id=None)
    admin.patch(f"/api/v1/time-entries/{e['id']}", json={"agreement_id": a["id"]})
    for action in ("ticket.update", "time_entry.update"):
        items = admin.get("/api/v1/audit", params={"action": action}).json()["items"]
        assert items[0]["before"]["agreement_id"] is None
        assert items[0]["after"]["agreement_id"] == a["id"]


# ---- agreement settings ---------------------------------------------------------------------
def test_settings_round_trip_and_defaults(admin, biller, org_ctx):
    flat = agreement(biller, org_ctx["org"], "flat")
    assert (flat["all_inclusive"], flat["rollover"], flat["rollover_cap_minutes"]) == (
        False,
        "expire",
        None,
    )
    block = agreement(biller, org_ctx["org"], rollover="roll", rollover_cap_minutes=300)
    assert (block["rollover"], block["rollover_cap_minutes"]) == ("roll", 300)
    r = biller.patch(f"/api/v1/agreements/{flat['id']}", json={"all_inclusive": True})
    assert r.status_code == 200 and r.json()["all_inclusive"] is True
    r = biller.patch(f"/api/v1/agreements/{block['id']}", json={"rollover_cap_minutes": None})
    assert r.status_code == 200 and r.json()["rollover_cap_minutes"] is None
    assert r.json()["rollover"] == "roll"
    items = admin.get("/api/v1/audit", params={"action": "agreement.update"}).json()["items"]
    assert items[0]["before"]["rollover_cap_minutes"] == 300
    assert items[0]["after"]["rollover_cap_minutes"] is None
    # leaving a type drops the settings that only apply to it
    r = biller.patch(
        f"/api/v1/agreements/{block['id']}", json={"type": "flat", "unit_price_cents": 500}
    )
    assert r.status_code == 200, r.text
    assert (r.json()["rollover"], r.json()["block_minutes"]) == ("expire", None)
    r = biller.patch(
        f"/api/v1/agreements/{flat['id']}", json={"type": "block", "block_minutes": 600}
    )
    assert r.status_code == 200 and r.json()["all_inclusive"] is False


@pytest.mark.parametrize(
    "type,kw",
    [
        ("block", {"all_inclusive": True}),
        ("per_user", {"all_inclusive": True}),
        ("flat", {"rollover": "roll"}),
        ("flat", {"rollover_cap_minutes": 60}),
        ("per_device", {"rollover": "roll"}),
        ("block", {"rollover_cap_minutes": 0}),
        ("block", {"rollover_cap_minutes": -60}),
        ("block", {"rollover": "forever"}),
    ],
)
def test_invalid_settings_are_422(biller, org_ctx, type, kw):
    body = {
        "organization_id": org_ctx["org"],
        "name": "Bad",
        "type": type,
        "unit_price_cents": 100,
        "start_date": "2026-01-01",
        **({"block_minutes": 600} if type == "block" else {}),
        **kw,
    }
    r = biller.post("/api/v1/agreements", json=body)
    assert r.status_code == 422, r.text
    assert biller.get("/api/v1/agreements").json() == []


def test_invalid_settings_on_update_are_422(biller, org_ctx):
    flat = agreement(biller, org_ctx["org"], "flat")
    block = agreement(biller, org_ctx["org"])
    for a, body in (
        (flat, {"rollover": "roll"}),
        (block, {"all_inclusive": True}),
        (block, {"rollover_cap_minutes": 0}),
        (flat, {"all_inclusive": True, "type": "block", "block_minutes": 600}),
    ):
        r = biller.patch(f"/api/v1/agreements/{a['id']}", json=body)
        assert r.status_code == 422, (body, r.text)


def test_tech_cannot_change_agreement_settings(login, biller, org_ctx):
    a = agreement(biller, org_ctx["org"], "flat")
    tech = login("tech")
    r = tech.patch(f"/api/v1/agreements/{a['id']}", json={"all_inclusive": True})
    assert r.status_code == 403
    body = {
        "organization_id": org_ctx["org"],
        "name": "x",
        "type": "flat",
        "unit_price_cents": 1,
        "start_date": "2026-01-01",
        "all_inclusive": True,
    }
    assert tech.post("/api/v1/agreements", json=body).status_code == 403


def test_database_guards(owner, biller, org_ctx):
    flat = agreement(biller, org_ctx["org"], "flat")
    block = agreement(biller, org_ctx["org"])
    for sql in (
        "UPDATE agreements SET all_inclusive = true WHERE id = :i",
        "UPDATE agreements SET rollover = 'forever' WHERE id = :i",
        "UPDATE agreements SET rollover_cap_minutes = 0 WHERE id = :i",
    ):
        with pytest.raises(IntegrityError):
            owner.execute(text(sql), {"i": block["id"]})
    owner.execute(
        text("UPDATE agreements SET all_inclusive = true WHERE id = :i"), {"i": flat["id"]}
    )
