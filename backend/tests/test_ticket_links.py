"""Parity phase 1D: ticket links and close-as-duplicate."""

import pytest
from sqlalchemy import text

from app.db import new_session, set_org_scope


@pytest.fixture
def three(admin, make_org):
    org = make_org("Link Co")["id"]
    ts = [
        admin.post("/api/tickets", json={"organization_id": org, "subject": f"T{i}"}).json()
        for i in range(3)
    ]
    return org, ts


def link(admin, t, relation, other):
    return admin.post(
        f"/api/tickets/{t['id']}/links",
        json={"relation": relation, "other_number": other["number"]},
    )


def rels(admin, t):
    return {(x["relation"], x["number"]) for x in admin.get(f"/api/tickets/{t['id']}/links").json()}


def test_relations_read_from_both_sides(admin, three):
    _, (a, b, c) = three
    assert link(admin, a, "related", b).status_code == 201
    assert link(admin, a, "child", c).status_code == 201  # c is a's child
    assert rels(admin, a) == {("related", b["number"]), ("child", c["number"])}
    assert rels(admin, b) == {("related", a["number"])}
    assert rels(admin, c) == {("parent", a["number"])}
    listed = admin.get(f"/api/tickets/{a['id']}/links").json()[0]
    assert listed["subject"] == "T1" and listed["status_name"] == "New"


def test_duplicate_direction(admin, three):
    _, (a, b, _) = three
    assert link(admin, a, "duplicate_of", b).status_code == 201
    assert rels(admin, a) == {("duplicate_of", b["number"])}
    assert rels(admin, b) == {("has_duplicate", a["number"])}


def test_link_rules(admin, three, make_org):
    org, (a, b, c) = three
    assert link(admin, a, "related", a).status_code == 409  # itself
    assert (
        admin.post(
            f"/api/tickets/{a['id']}/links", json={"relation": "related", "other_number": 999999}
        ).status_code
        == 404
    )
    other_org = make_org("Elsewhere")["id"]
    foreign = admin.post("/api/tickets", json={"organization_id": other_org, "subject": "F"}).json()
    assert link(admin, a, "related", foreign).status_code == 409  # different client
    assert (
        admin.post(
            f"/api/tickets/{a['id']}/links", json={"relation": "bogus", "other_number": 1}
        ).status_code
        == 422
    )
    assert link(admin, a, "related", b).status_code == 201
    assert link(admin, b, "related", a).status_code == 409  # one link per pair, either way
    assert link(admin, a, "duplicate_of", b).status_code == 409
    # a ticket has at most one original and one parent
    assert link(admin, a, "duplicate_of", c).status_code == 201
    assert link(admin, b, "duplicate_of", c).status_code == 201
    d = admin.post("/api/tickets", json={"organization_id": org, "subject": "D"}).json()
    assert link(admin, a, "duplicate_of", d).status_code == 409
    # c is an original; it cannot itself be a duplicate, nor can a duplicate have duplicates
    assert link(admin, c, "duplicate_of", d).status_code == 409
    assert link(admin, d, "duplicate_of", a).status_code == 409


def test_parent_rules_and_cycles(admin, three):
    _, (a, b, c) = three
    assert link(admin, a, "child", b).status_code == 201
    assert link(admin, b, "child", c).status_code == 201
    assert link(admin, c, "child", a).status_code == 409  # a -> b -> c -> a
    assert link(admin, a, "parent", c).status_code == 409  # c would be a's parent: c is below a
    assert link(admin, c, "parent", a).status_code == 409  # c already has a parent (b)... or a pair


def test_remove_link_is_audited_and_scoped(admin, three, owner):
    _, (a, b, c) = three
    l1 = link(admin, a, "related", b)
    lid = admin.get(f"/api/tickets/{a['id']}/links").json()[0]["id"]
    assert l1.status_code == 201
    assert admin.delete(f"/api/tickets/{c['id']}/links/{lid}").status_code == 404  # not c's link
    assert admin.delete(f"/api/tickets/{b['id']}/links/{lid}").status_code == 204
    assert rels(admin, a) == set()
    assert admin.delete(f"/api/tickets/{b['id']}/links/{lid}").status_code == 404
    actions = {
        r[0]
        for r in owner.execute(
            text("SELECT action FROM audit_log WHERE action LIKE 'ticket.link%'")
        )
    }
    assert actions == {"ticket.link_add", "ticket.link_remove"}


def test_permissions(admin, login, three):
    _, (a, b, _) = three
    ro, tech = login("read_only"), login("tech")
    assert ro.get(f"/api/tickets/{a['id']}/links").status_code == 200
    assert link(ro, a, "related", b).status_code == 403
    assert link(tech, a, "related", b).status_code == 201
    lid = tech.get(f"/api/tickets/{a['id']}/links").json()[0]["id"]
    assert ro.delete(f"/api/tickets/{a['id']}/links/{lid}").status_code == 403
    body = {"original_number": b["number"]}
    assert ro.post(f"/api/tickets/{a['id']}/close-as-duplicate", json=body).status_code == 403


def test_close_as_duplicate_keeps_history_where_it_was_written(admin, three, owner):
    _, (dup, original, _) = three
    admin.post(f"/api/tickets/{dup['id']}/notes", json={"body": "Customer's own words"})
    wt = admin.get("/api/work-types").json()[0]["id"]
    assert (
        admin.post(
            f"/api/tickets/{dup['id']}/time", json={"work_type_id": wt, "minutes": 30}
        ).status_code
        == 201
    )
    r = admin.post(
        f"/api/tickets/{dup['id']}/close-as-duplicate", json={"original_number": original["number"]}
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "closed" and r.json()["closed_at"]
    assert rels(admin, dup) == {("duplicate_of", original["number"])}
    assert rels(admin, original) == {("has_duplicate", dup["number"])}
    dup_notes = [n["body"] for n in admin.get(f"/api/tickets/{dup['id']}/notes").json()]
    orig_notes = [n["body"] for n in admin.get(f"/api/tickets/{original['id']}/notes").json()]
    assert "Customer's own words" in dup_notes
    assert any("duplicate of #" in n for n in dup_notes)
    assert any(f"#{dup['number']}" in n and "duplicate of this" in n for n in orig_notes)
    # pointer notes are internal: a client never sees them
    vis = {n["visibility"] for n in admin.get(f"/api/tickets/{original['id']}/notes").json()}
    assert vis == {"internal"}
    # time stayed on the duplicate, none on the original
    assert len(admin.get(f"/api/tickets/{dup['id']}/time").json()) == 1
    assert admin.get(f"/api/tickets/{original['id']}/time").json() == []
    got = {
        r[0]
        for r in owner.execute(
            text("SELECT action FROM audit_log WHERE action = 'ticket.close_duplicate'")
        )
    }
    assert got == {"ticket.close_duplicate"}


def test_close_as_duplicate_rules(admin, three, make_org):
    org, (a, b, c) = three
    body = {"original_number": b["number"]}
    assert (
        admin.post(
            f"/api/tickets/{a['id']}/close-as-duplicate", json={"original_number": a["number"]}
        ).status_code
        == 409
    )
    foreign = admin.post(
        "/api/tickets", json={"organization_id": make_org("Else")["id"], "subject": "F"}
    ).json()
    assert (
        admin.post(
            f"/api/tickets/{a['id']}/close-as-duplicate",
            json={"original_number": foreign["number"]},
        ).status_code
        == 409
    )
    assert admin.post(f"/api/tickets/{a['id']}/close-as-duplicate", json=body).status_code == 200
    # already closed; and a failed attempt leaves no half-done link behind
    assert admin.post(f"/api/tickets/{a['id']}/close-as-duplicate", json=body).status_code == 409
    assert (
        admin.post(
            f"/api/tickets/{c['id']}/close-as-duplicate", json={"original_number": a["number"]}
        ).status_code
        == 409
    )  # a is itself a duplicate
    assert rels(admin, c) == set()
    assert admin.get(f"/api/tickets/{c['id']}").json()["status"] == "new"


def test_links_are_scoped_by_row_level_security(admin, three, make_org):
    org, (a, b, _) = three
    link(admin, a, "related", b)
    other = make_org("Second")["id"]
    x = admin.post("/api/tickets", json={"organization_id": other, "subject": "X"}).json()
    y = admin.post("/api/tickets", json={"organization_id": other, "subject": "Y"}).json()
    link(admin, x, "related", y)
    with new_session() as db:
        assert db.execute(text("SELECT count(*) FROM ticket_links")).scalar_one() == 0
        set_org_scope(db, str(org))
        orgs = {r[0] for r in db.execute(text("SELECT organization_id FROM ticket_links"))}
        assert orgs == {org}
