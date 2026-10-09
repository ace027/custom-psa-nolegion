"""Parity phase 1C: ticket types and custom fields."""

import pytest
from sqlalchemy import text

from tests.test_portal import (  # noqa: F401  (fixtures)
    add_contact,
    link_emails,
    portal_on,
    sign_in,
    two_clients,
)


@pytest.fixture
def ttype(admin):
    r = admin.post("/api/ticket-types", json={"name": "New hire"})
    assert r.status_code == 201, r.text
    return r.json()


def add_field(admin, type_id, **kw):
    body = {"name": "Field", "field_type": "text", **kw}
    r = admin.post(f"/api/ticket-types/{type_id}/fields", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_type_lifecycle_audit_and_unique_name(admin, ttype):
    assert admin.post("/api/ticket-types", json={"name": "new HIRE"}).status_code == 409
    assert (
        admin.patch(f"/api/ticket-types/{ttype['id']}", json={"name": "Onboarding"}).status_code
        == 200
    )
    assert admin.post(f"/api/ticket-types/{ttype['id']}/archive").status_code == 200
    names = [t["name"] for t in admin.get("/api/ticket-types").json()]
    assert "Onboarding" not in names
    assert any(
        t["name"] == "Onboarding"
        for t in admin.get("/api/ticket-types", params={"include_archived": True}).json()
    )


def test_field_definition_rules(admin, ttype):
    tid = ttype["id"]
    f = add_field(admin, tid, name="Start date", field_type="date", required=True)
    assert f["position"] > 0 and f["options"] is None
    # duplicate active name (case-insensitive)
    r = admin.post(
        f"/api/ticket-types/{tid}/fields", json={"name": "start DATE", "field_type": "text"}
    )
    assert r.status_code == 409
    # dropdown needs options; others forbid them
    bad = {"name": "Laptop", "field_type": "dropdown"}
    assert admin.post(f"/api/ticket-types/{tid}/fields", json=bad).status_code == 409
    dup = {**bad, "options": ["a", "A"]}
    assert admin.post(f"/api/ticket-types/{tid}/fields", json=dup).status_code == 409
    not_dd = {"name": "Note", "field_type": "text", "options": ["x"]}
    assert admin.post(f"/api/ticket-types/{tid}/fields", json=not_dd).status_code == 409
    assert (
        admin.post(
            f"/api/ticket-types/{tid}/fields", json={"name": "X", "field_type": "bogus"}
        ).status_code
        == 422
    )
    assert admin.post("/api/ticket-types/99999/fields", json=bad).status_code == 404
    # type is immutable; options editable on dropdown only
    dd = add_field(admin, tid, name="Laptop", field_type="dropdown", options=["Dell", "HP"])
    p = admin.patch(f"/api/custom-fields/{dd['id']}", json={"options": ["Dell", "HP", "Lenovo"]})
    assert p.status_code == 200 and p.json()["options"] == ["Dell", "HP", "Lenovo"]
    assert admin.patch(f"/api/custom-fields/{f['id']}", json={"options": ["x"]}).status_code == 409
    assert (
        admin.patch(f"/api/custom-fields/{f['id']}", json={"field_type": "text"}).json()[
            "field_type"
        ]
        == "date"
    )
    # archive / unarchive and listing
    assert admin.post(f"/api/custom-fields/{dd['id']}/archive").status_code == 200
    assert [x["name"] for x in admin.get(f"/api/ticket-types/{tid}/fields").json()] == [
        "Start date"
    ]
    assert len(admin.get(f"/api/ticket-types/{tid}/fields?include_archived=true").json()) == 2
    assert admin.post(f"/api/custom-fields/{dd['id']}/unarchive").status_code == 200
    assert admin.get("/api/ticket-types/99999/fields").status_code == 404


def test_values_validated_per_type(admin, ttype, make_ticket):
    tid = ttype["id"]
    fs = {
        k: add_field(
            admin, tid, name=k, field_type=k, options=["Dell", "HP"] if k == "dropdown" else None
        )
        for k in ("text", "number", "date", "dropdown", "checkbox")
    }
    t = make_ticket(type_id=tid)
    assert t["type_name"] == "New hire" and t["custom_values"] == {}

    def put(**vals):
        body = {"custom_values": {str(fs[k]["id"]): v for k, v in vals.items()}}
        return admin.patch(f"/api/tickets/{t['id']}", json=body)

    ok = put(text=" hello ", number=3.5, date="2026-03-04", dropdown="HP", checkbox=True)
    assert ok.status_code == 200, ok.text
    cv = ok.json()["custom_values"]
    assert cv[str(fs["text"]["id"])] == "hello" and cv[str(fs["number"]["id"])] == 3.5
    for bad in (
        {"number": "3"},
        {"number": True},
        {"date": "03/04/2026"},
        {"date": "2026-02-30"},
        {"dropdown": "Acer"},
        {"checkbox": "yes"},
        {"text": 5},
        {"text": "x" * 2001},
    ):
        assert put(**bad).status_code == 409, bad
    # unknown field id
    assert (
        admin.patch(f"/api/tickets/{t['id']}", json={"custom_values": {"99999": "x"}}).status_code
        == 409
    )
    # blank / null clears
    cleared = put(text="", number=None)
    cv = cleared.json()["custom_values"]
    assert str(fs["text"]["id"]) not in cv and str(fs["number"]["id"]) not in cv
    assert str(fs["date"]["id"]) in cv  # untouched
    # the per-ticket view lists definitions with values
    view = admin.get(f"/api/tickets/{t['id']}/custom-fields").json()
    assert [v["name"] for v in view] == ["text", "number", "date", "dropdown", "checkbox"]
    assert next(v for v in view if v["name"] == "date")["value"] == "2026-03-04"


def test_required_fields_are_enforced_on_create_and_type_change(admin, ttype, make_ticket):
    tid = ttype["id"]
    req = add_field(admin, tid, name="Manager", required=True)
    box = add_field(admin, tid, name="Approved", field_type="checkbox", required=True)
    # create with the type but without the required values
    org = admin.post("/api/organizations", json={"name": "Req Co"}).json()["id"]
    r = admin.post("/api/tickets", json={"organization_id": org, "subject": "S", "type_id": tid})
    assert r.status_code == 409 and "Manager" in r.json()["detail"]
    r = admin.post(
        "/api/tickets",
        json={
            "organization_id": org,
            "subject": "S",
            "type_id": tid,
            "custom_values": {str(req["id"]): "Sam", str(box["id"]): False},
        },
    )
    assert r.status_code == 409 and "Approved" in r.json()["detail"]
    ok = admin.post(
        "/api/tickets",
        json={
            "organization_id": org,
            "subject": "S",
            "type_id": tid,
            "custom_values": {str(req["id"]): "Sam", str(box["id"]): True},
        },
    )
    assert ok.status_code == 201, ok.text
    # an untyped ticket cannot be switched to the type without values
    plain = make_ticket()
    assert admin.patch(f"/api/tickets/{plain['id']}", json={"type_id": tid}).status_code == 409
    sw = admin.patch(
        f"/api/tickets/{plain['id']}",
        json={
            "type_id": tid,
            "custom_values": {str(req["id"]): "Kim", str(box["id"]): True},
        },
    )
    assert sw.status_code == 200 and sw.json()["type_name"] == "New hire"
    # ordinary edits do not re-demand required fields
    assert (
        admin.patch(f"/api/tickets/{ok.json()['id']}", json={"subject": "New"}).status_code == 200
    )
    # clearing the type is allowed and keeps the stored values
    cleared = admin.patch(f"/api/tickets/{plain['id']}", json={"type_id": None})
    assert cleared.status_code == 200 and cleared.json()["type_id"] is None
    assert cleared.json()["custom_values"][str(req["id"])] == "Kim"
    assert admin.get(f"/api/tickets/{plain['id']}/custom-fields").json() == []


def test_switching_type_retains_old_values_and_rejects_foreign_fields(admin, ttype, make_ticket):
    other = admin.post("/api/ticket-types", json={"name": "Outage"}).json()
    mine = add_field(admin, ttype["id"], name="Laptop")
    theirs = add_field(admin, other["id"], name="Site")
    t = make_ticket(type_id=ttype["id"], custom_values={str(mine["id"]): "Dell"})
    # a field from another type is unknown here
    bad = admin.patch(f"/api/tickets/{t['id']}", json={"custom_values": {str(theirs["id"]): "x"}})
    assert bad.status_code == 409
    sw = admin.patch(
        f"/api/tickets/{t['id']}",
        json={"type_id": other["id"], "custom_values": {str(theirs["id"]): "HQ"}},
    )
    assert sw.status_code == 200
    assert sw.json()["custom_values"] == {str(mine["id"]): "Dell", str(theirs["id"]): "HQ"}
    assert [v["name"] for v in admin.get(f"/api/tickets/{t['id']}/custom-fields").json()] == [
        "Site"
    ]
    back = admin.patch(f"/api/tickets/{t['id']}", json={"type_id": ttype["id"]})
    assert back.status_code == 200
    assert admin.get(f"/api/tickets/{t['id']}/custom-fields").json()[0]["value"] == "Dell"


def test_archived_type_and_field_rules(admin, ttype, make_ticket):
    f = add_field(admin, ttype["id"], name="Laptop")
    t = make_ticket(type_id=ttype["id"], custom_values={str(f["id"]): "Dell"})
    admin.post(f"/api/custom-fields/{f['id']}/archive")
    assert admin.get(f"/api/tickets/{t['id']}/custom-fields").json() == []
    assert admin.get(f"/api/tickets/{t['id']}").json()["custom_values"] == {str(f["id"]): "Dell"}
    assert (
        admin.patch(
            f"/api/tickets/{t['id']}", json={"custom_values": {str(f["id"]): "HP"}}
        ).status_code
        == 409
    )
    admin.post(f"/api/ticket-types/{ttype['id']}/archive")
    # an archived type cannot be chosen for a new ticket or gain fields
    r = admin.post(
        "/api/tickets",
        json={"organization_id": t["organization_id"], "subject": "S", "type_id": ttype["id"]},
    )
    assert r.status_code == 409
    nf = admin.post(
        f"/api/ticket-types/{ttype['id']}/fields", json={"name": "N", "field_type": "text"}
    )
    assert nf.status_code == 409
    assert admin.post(f"/api/custom-fields/{f['id']}/unarchive").status_code == 409
    # the ticket keeps its (archived) type
    assert admin.get(f"/api/tickets/{t['id']}").json()["type_name"] == "New hire"


def test_type_filter_on_ticket_list(admin, ttype, make_ticket):
    a = make_ticket(type_id=ttype["id"])
    make_ticket()
    got = admin.get("/api/tickets", params={"type_id": ttype["id"]}).json()
    assert [x["id"] for x in got["items"]] == [a["id"]]


def test_permissions(admin, login, ttype):
    f = add_field(admin, ttype["id"], name="F")
    tech, ro = login("tech"), login("read_only")
    for c in (tech, ro):
        assert c.get(f"/api/ticket-types/{ttype['id']}/fields").status_code == 200
    for c in (tech, ro):
        assert (
            c.post(
                f"/api/ticket-types/{ttype['id']}/fields", json={"name": "Z", "field_type": "text"}
            ).status_code
            == 403
        )
        assert c.patch(f"/api/custom-fields/{f['id']}", json={"name": "Q"}).status_code == 403
        assert c.post(f"/api/custom-fields/{f['id']}/archive").status_code == 403
        assert c.post(f"/api/custom-fields/{f['id']}/unarchive").status_code == 403
        assert c.post("/api/ticket-types", json={"name": "Nope"}).status_code == 403
    # read-only cannot write custom values; techs can
    t = admin.post(
        "/api/tickets",
        json={
            "organization_id": admin.post("/api/organizations", json={"name": "P Co"}).json()["id"],
            "subject": "S",
        },
    ).json()
    body = {"type_id": ttype["id"], "custom_values": {str(f["id"]): "v"}}
    assert ro.patch(f"/api/tickets/{t['id']}", json=body).status_code == 403
    assert tech.patch(f"/api/tickets/{t['id']}", json=body).status_code == 200


def test_changes_are_audited(admin, ttype, make_ticket, owner):
    f = add_field(admin, ttype["id"], name="F")
    admin.patch(f"/api/custom-fields/{f['id']}", json={"name": "G"})
    admin.post(f"/api/custom-fields/{f['id']}/archive")
    admin.post(f"/api/custom-fields/{f['id']}/unarchive")
    actions = {
        r[0]
        for r in owner.execute(
            text(
                "SELECT action FROM audit_log WHERE action LIKE 'custom_field.%' OR "
                "action LIKE 'ticket_type.%'"
            )
        )
    }
    assert {
        "ticket_type.create",
        "custom_field.create",
        "custom_field.update",
        "custom_field.archive",
        "custom_field.unarchive",
    } <= actions


def test_portal_shows_only_client_visible_filled_fields(admin, ttype, sign_in, two_clients):
    a, _ = two_clients
    pat = add_contact(admin, a, "Pat", "pat@acme.com")
    shown = add_field(admin, ttype["id"], name="Laptop model", client_visible=True)
    hidden = add_field(admin, ttype["id"], name="Internal cost code")
    empty = add_field(admin, ttype["id"], name="Shown but empty", client_visible=True)
    assert empty
    t = admin.post(
        "/api/tickets",
        json={
            "organization_id": a,
            "contact_id": pat["id"],
            "subject": "Hire",
            "type_id": ttype["id"],
            "custom_values": {str(shown["id"]): "Dell 5440", str(hidden["id"]): "SECRET-77"},
        },
    )
    assert t.status_code == 201, t.text
    d = sign_in("pat@acme.com").get(f"/api/portal/tickets/{t.json()['id']}")
    assert "SECRET-77" not in d.text and "Internal cost code" not in d.text
    assert d.json()["custom_fields"] == [{"name": "Laptop model", "value": "Dell 5440"}]
