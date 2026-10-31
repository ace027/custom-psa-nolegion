"""Knowledge base: staff API, search, permissions, audit and ticket suggestions."""

import pytest
from sqlalchemy import text

from app import seed


def article(admin, title="Reset a password", body="Open the portal and reset it.", **kw):
    r = admin.post(
        "/api/v1/kb/articles",
        json={"title": title, "body": body, "visibility": "client", **kw},
    )
    assert r.status_code == 201, r.text
    return r.json()


def search(c, q, **params):
    r = c.get("/api/v1/kb/articles", params={"q": q, **params})
    assert r.status_code == 200, r.text
    return r.json()


def test_create_get_patch_round_trip_with_audit(admin, owner):
    a = article(admin, tags=["VPN", " vpn ", "Network"])
    assert a["status"] == "draft" and a["tags"] == ["vpn", "network"]
    assert a["created_by_name"] == "admin user" and a["updated_by_name"] == "admin user"
    assert admin.get(f"/api/v1/kb/articles/{a['id']}").json()["title"] == "Reset a password"
    r = admin.patch(
        f"/api/v1/kb/articles/{a['id']}", json={"status": "published", "title": "New title"}
    )
    assert r.status_code == 200 and r.json()["status"] == "published"
    assert r.json()["title"] == "New title" and r.json()["body"] == a["body"]
    rows = owner.execute(
        text(
            "SELECT action, before, after FROM audit_log WHERE entity_type='kb_articles' ORDER BY id"
        )
    ).all()
    assert [x.action for x in rows] == ["kb_article.create", "kb_article.update"]
    assert rows[1].before["status"] == "draft" and rows[1].after["status"] == "published"
    assert "search" not in rows[1].after


def test_missing_article_is_404(admin):
    assert admin.get("/api/v1/kb/articles/999").status_code == 404
    assert admin.patch("/api/v1/kb/articles/999", json={"title": "x"}).status_code == 404


def test_validation(admin):
    base = {"title": "T", "body": "B", "visibility": "client"}
    post = lambda **kw: admin.post("/api/v1/kb/articles", json={**base, **kw})  # noqa: E731
    assert post(title="   ").status_code == 422
    assert post(body="").status_code == 422
    assert post(visibility="public").status_code == 422
    assert post(tags=[f"t{i}" for i in range(11)]).status_code == 422
    assert post(tags=["x" * 41]).status_code == 422
    assert post(tags=["  "]).status_code == 422
    ok = post(tags=[f"t{i}" for i in range(10)])
    assert ok.status_code == 201 and len(ok.json()["tags"]) == 10
    mixed = post(tags=["Alpha", "ALPHA", "beta", "alpha"]).json()
    assert mixed["tags"] == ["alpha", "beta"]
    pid = admin.post("/api/v1/kb/articles", json=base).json()["id"]
    assert admin.patch(f"/api/v1/kb/articles/{pid}", json={"tags": ["A"] * 11}).status_code == 422
    assert admin.patch(f"/api/v1/kb/articles/{pid}", json={"tags": ["A", "a"]}).json()["tags"] == [
        "a"
    ]


def test_permissions(login, admin):
    a = article(admin)
    body = {"title": "T", "body": "B", "visibility": "internal"}
    for role in ("read_only", "billing"):
        c = login(role)
        assert c.get("/api/v1/kb/articles").status_code == 200
        assert c.get(f"/api/v1/kb/articles/{a['id']}").status_code == 200
        assert c.post("/api/v1/kb/articles", json=body).status_code == 403
        assert c.patch(f"/api/v1/kb/articles/{a['id']}", json={"title": "x"}).status_code == 403
    tech = login("tech")
    assert tech.post("/api/v1/kb/articles", json=body).status_code == 201


def test_unauthenticated_is_401(anon):
    assert anon.get("/api/v1/kb/articles").status_code == 401
    assert anon.get("/api/v1/kb/suggestions", params={"ticket_id": 1}).status_code == 401


def test_search_ranks_title_above_body(admin):
    body_hit = article(admin, "General tips", "Sometimes the firewall blocks things.")
    title_hit = article(admin, "Firewall rules", "How to open a port.")
    ids = [i["id"] for i in search(admin, "firewall")["items"]]
    assert ids == [title_hit["id"], body_hit["id"]]
    assert search(admin, "firewall")["items"][0]["snippet"] == "How to open a port."


def test_websearch_syntax(admin):
    a = article(admin, "Mail flow", "the exact phrase lives here with printer")
    b = article(admin, "Mail flow two", "the exact phrase lives here with scanner")
    article(admin, "Other", "exact only, phrase elsewhere")
    got = {i["id"] for i in search(admin, '"exact phrase" -scanner')["items"]}
    assert got == {a["id"]}
    got = {i["id"] for i in search(admin, '"exact phrase"')["items"]}
    assert got == {a["id"], b["id"]}


def test_stop_word_only_query_falls_back_without_error(admin):
    article(admin, "What to do", "something")
    article(admin, "Unrelated", "something else")
    res = search(admin, "to do")
    assert [i["title"] for i in res["items"]] == ["What to do"]
    assert search(admin, "the")["items"] == []
    assert search(admin, "100%")["total"] == 0  # LIKE wildcards are escaped
    assert admin.get("/api/v1/kb/articles", params={"q": "a"}).status_code == 422


def test_filters_and_pagination(admin):
    a = article(admin, "One", "x", status="published")
    article(admin, "Two", "x", visibility="internal")
    c = article(admin, "Three", "x", status="archived")
    assert admin.get("/api/v1/kb/articles").json()["total"] == 3
    r = admin.get("/api/v1/kb/articles", params={"status": "published"}).json()
    assert [i["id"] for i in r["items"]] == [a["id"]]
    r = admin.get("/api/v1/kb/articles", params={"status": "archived"}).json()
    assert [i["id"] for i in r["items"]] == [c["id"]]
    r = admin.get("/api/v1/kb/articles", params={"visibility": "internal"}).json()
    assert r["total"] == 1
    page = admin.get("/api/v1/kb/articles", params={"limit": 2, "offset": 2}).json()
    assert page["total"] == 3 and len(page["items"]) == 1 and page["limit"] == 2
    assert admin.get("/api/v1/kb/articles", params={"limit": 101}).status_code == 422
    assert admin.get("/api/v1/kb/articles", params={"offset": -1}).status_code == 422
    assert search(admin, "One", status="published")["total"] == 1
    assert search(admin, "One", status="archived")["total"] == 0


def test_snippet_is_first_200_chars(admin):
    a = article(admin, "Long", "a" * 500)
    item = admin.get("/api/v1/kb/articles").json()["items"][0]
    assert item["id"] == a["id"] and item["snippet"] == "a" * 200
    assert "body" not in item


def test_suggestions(admin, make_ticket):
    match = article(admin, "Printer offline fix", "Restart the spooler.", status="published")
    internal = article(
        admin,
        "Printer spooler runbook",
        "Printer notes",
        visibility="internal",
        status="published",
    )
    article(admin, "Printer draft", "printer", status="draft")
    article(admin, "Printer old", "printer", status="archived")
    article(admin, "Unrelated", "Nothing here", status="published")
    t = make_ticket(subject="Front desk printer offline")
    r = admin.get("/api/v1/kb/suggestions", params={"ticket_id": t["id"]})
    assert r.status_code == 200
    ids = [i["id"] for i in r.json()]
    assert set(ids) == {match["id"], internal["id"]}
    assert ids[0] == match["id"]  # more of the ticket words in the title


def test_suggestions_cap_at_five(admin, make_ticket):
    for i in range(7):
        article(admin, f"Printer help {i}", "printer", status="published")
    t = make_ticket(subject="printer")
    assert len(admin.get("/api/v1/kb/suggestions", params={"ticket_id": t["id"]}).json()) == 5


def test_suggestions_with_no_usable_words(admin, make_ticket):
    article(admin, "Printer", "printer", status="published")
    t = make_ticket(subject="a b !!")
    assert admin.get("/api/v1/kb/suggestions", params={"ticket_id": t["id"]}).json() == []


def test_suggestions_survive_tsquery_operators(admin, make_ticket):
    article(admin, "Cannot print", "printer", status="published")
    for subject in ["can't & | ! :*", "(printer) <-> 'x' \\ ' \" print", "printer:* & !cannot"]:
        t = make_ticket(subject=subject)
        r = admin.get("/api/v1/kb/suggestions", params={"ticket_id": t["id"]})
        assert r.status_code == 200, subject


def test_suggestions_ticket_outside_scope_is_404(admin, login, make_ticket):
    t = make_ticket()
    assert admin.get("/api/v1/kb/suggestions", params={"ticket_id": 99999}).status_code == 404
    assert admin.get("/api/v1/kb/suggestions", params={"ticket_id": t["id"]}).status_code == 200
    assert admin.get("/api/v1/kb/suggestions").status_code == 422


def test_suggestions_ticket_in_another_orgs_scope_is_404(admin, make_ticket):
    from app.scope import Scope

    t = make_ticket()
    other = t["organization_id"] + 1000
    from app import kb as kbsvc
    from app.db import new_session
    from app.deps import Ctx

    with new_session() as db:
        ctx = Ctx(db=db, user=None, scope=Scope.orgs(other))
        from app.errors import NotFound

        with pytest.raises(NotFound):
            kbsvc.suggestions_for_ticket(ctx, t["id"])


def test_seed_adds_four_articles_once(owner):
    seed.run()
    seed.run()
    rows = owner.execute(
        text("SELECT visibility, status, count(*) n FROM kb_articles GROUP BY 1, 2")
    ).all()
    assert sum(r.n for r in rows) == 4
    got = {(r.visibility, r.status): r.n for r in rows}
    assert got == {
        ("client", "published"): 2,
        ("internal", "published"): 1,
        ("internal", "draft"): 1,
    }
