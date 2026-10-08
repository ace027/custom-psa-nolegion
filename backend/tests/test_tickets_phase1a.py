"""Parity phase 1, slice A: canned responses, bulk actions, sorting, global search."""


def pri(admin, name):
    return next(p["id"] for p in admin.get("/api/priorities").json() if p["name"] == name)


# ---- canned responses ----
def test_canned_responses_crud_unique_and_archive(admin):
    r = admin.post(
        "/api/canned-responses", json={"name": "Reset done", "body": "Hi {{contact_name}}"}
    )
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    assert (
        admin.post("/api/canned-responses", json={"name": "reset DONE", "body": "x"}).status_code
        == 409
    )
    assert (
        admin.post("/api/canned-responses", json={"name": "Blank", "body": "   "}).status_code
        == 422
    )
    p = admin.patch(f"/api/canned-responses/{cid}", json={"body": "Updated"})
    assert p.status_code == 200 and p.json()["body"] == "Updated"
    assert admin.post(f"/api/canned-responses/{cid}/archive").status_code == 200
    assert cid not in [c["id"] for c in admin.get("/api/canned-responses").json()]
    # archived name can be reused
    assert (
        admin.post("/api/canned-responses", json={"name": "Reset done", "body": "y"}).status_code
        == 201
    )
    actions = [
        a["action"]
        for a in admin.get("/api/audit", params={"action": "canned_response."}).json()["items"]
    ]
    assert "canned_response.create" in actions and "canned_response.archive" in actions


def test_canned_responses_permissions(login, admin):
    tech = login("tech")
    ro = login("read_only")
    assert tech.get("/api/canned-responses").status_code == 200
    assert ro.get("/api/canned-responses").status_code == 200
    body = {"name": "X", "body": "y"}
    assert tech.post("/api/canned-responses", json=body).status_code == 403
    assert ro.post("/api/canned-responses", json=body).status_code == 403
    cid = admin.post("/api/canned-responses", json=body).json()["id"]
    assert tech.patch(f"/api/canned-responses/{cid}", json={"body": "z"}).status_code == 403
    assert tech.post(f"/api/canned-responses/{cid}/archive").status_code == 403


# ---- bulk ----
def test_bulk_update_changes_and_audits(admin, make_ticket):
    ts = [make_ticket(subject=f"T{i}") for i in range(3)]
    ids = [t["id"] for t in ts]
    high = pri(admin, "High")
    r = admin.post(
        "/api/tickets/bulk",
        json={"ticket_ids": ids, "changes": {"priority_id": high, "status": "open"}},
    )
    assert r.status_code == 200, r.text
    assert r.json()["updated"] == 3 and r.json()["failed"] == []
    for i in ids:
        t = admin.get(f"/api/tickets/{i}").json()
        assert t["priority_id"] == high and t["status"] == "open"
    actions = [
        a["action"] for a in admin.get("/api/audit", params={"action": "ticket."}).json()["items"]
    ]
    assert "ticket.bulk_update" in actions


def test_bulk_partial_failure_keeps_the_rest(admin, make_ticket):
    t1, t2 = make_ticket(), make_ticket()
    r = admin.post(
        "/api/tickets/bulk",
        json={"ticket_ids": [t1["id"], 999999, t2["id"], t1["id"]], "changes": {"status": "open"}},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["updated"] == 2
    assert [f["id"] for f in body["failed"]] == [999999]
    assert admin.get(f"/api/tickets/{t1['id']}").json()["status"] == "open"


def test_bulk_validation_and_permissions(admin, login, make_ticket):
    t = make_ticket()
    assert admin.post(
        "/api/tickets/bulk", json={"ticket_ids": [t["id"]], "changes": {}}
    ).status_code in (409, 422)
    assert (
        admin.post(
            "/api/tickets/bulk", json={"ticket_ids": [], "changes": {"status": "open"}}
        ).status_code
        == 422
    )
    too_many = list(range(1, 102))
    assert (
        admin.post(
            "/api/tickets/bulk", json={"ticket_ids": too_many, "changes": {"status": "open"}}
        ).status_code
        == 422
    )
    ro = login("read_only")
    assert (
        ro.post(
            "/api/tickets/bulk", json={"ticket_ids": [t["id"]], "changes": {"status": "open"}}
        ).status_code
        == 403
    )


# ---- sorting and paging ----
def test_ticket_sorting_and_paging(admin, make_ticket):
    low, high = pri(admin, "Low"), pri(admin, "High")
    a = make_ticket(subject="A", priority_id=low)
    b = make_ticket(subject="B", priority_id=high)
    c = make_ticket(subject="C")
    nums = lambda **p: [t["id"] for t in admin.get("/api/tickets", params=p).json()["items"]]  # noqa: E731
    assert nums(sort="number", descending="false") == [a["id"], b["id"], c["id"]]
    assert nums(sort="number") == [c["id"], b["id"], a["id"]]
    pr = nums(sort="priority", descending="false")
    assert pr[0] == b["id"] and pr[-1] == a["id"]
    assert len(nums(sort="due")) == 3
    page = admin.get("/api/tickets", params={"sort": "number", "limit": 2, "offset": 2}).json()
    assert page["total"] == 3 and [t["id"] for t in page["items"]] == [a["id"]]
    assert admin.get("/api/tickets", params={"sort": "bogus"}).status_code == 422


# ---- search ----
def test_search_finds_across_kinds_and_escapes_wildcards(admin, org_ctx, make_ticket):
    make_ticket(subject="Printer 100% jammed")
    make_ticket(subject="Printer 100 fine")
    admin.post(
        f"/api/organizations/{org_ctx['org']}/contacts",
        json={"name": "Zed Zebra", "email": "zed@acme.com"},
    )
    hits = admin.get("/api/search", params={"q": "100%"}).json()["hits"]
    assert [h["title"] for h in hits if h["kind"] == "ticket"] == [
        "#10001 Printer 100% jammed"
    ] or len([h for h in hits if h["kind"] == "ticket"]) == 1
    kinds = {h["kind"] for h in admin.get("/api/search", params={"q": "acme"}).json()["hits"]}
    assert {"organization", "contact"} <= kinds
    assert [h["kind"] for h in admin.get("/api/search", params={"q": "zebra"}).json()["hits"]] == [
        "contact"
    ]
    by_number = admin.get("/api/search", params={"q": "#10001"}).json()["hits"]
    assert by_number and by_number[0]["kind"] == "ticket"
    assert admin.get("/api/search", params={"q": "a"}).status_code == 422
    assert admin.get("/api/search", params={"q": "%%"}).json()["hits"] == []


def test_search_requires_login(anon):
    assert anon.get("/api/search", params={"q": "acme"}).status_code == 401
