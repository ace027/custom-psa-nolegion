"""Project routes: the admin flow, permission failures and error mapping."""

import pytest


@pytest.fixture
def org(make_org):
    return make_org("Proj Client")["id"]


@pytest.fixture
def tech(login):
    return login("tech")


@pytest.fixture
def read_only(login):
    return login("read_only")


def create(client, org, **extra):
    r = client.post("/api/projects", json={"organization_id": org, "name": "Rollout", **extra})
    assert r.status_code == 201, r.text
    return r.json()


def add_task(client, pid, title="Task", **extra):
    r = client.post(f"/api/projects/{pid}/tasks", json={"title": title, **extra})
    assert r.status_code == 201, r.text
    return r.json()


def test_admin_full_flow(admin, org, wt, log, make_user):
    tech_user = make_user("tech", "worker@example.com")
    p = create(admin, org, description="Office move", billing_mode="tm", budget_cents=50_000)
    pid = p["id"]
    assert p["status"] == "draft" and p["tasks"] == [] and p["phases"] == []
    assert p["budget"]["remaining_cents"] == 50_000 and p["fixed_fee_billed"] is False
    assert p["organization_name"] == "Proj Client"

    ph = admin.post(f"/api/projects/{pid}/phases", json={"name": "Plan"})
    assert ph.status_code == 201 and ph.json()["task_count"] == 0
    phase_id = ph.json()["id"]

    t1 = add_task(
        admin, pid, "Survey", phase_id=phase_id, estimate_minutes=60, assignee_id=tech_user["id"]
    )
    t2 = add_task(admin, pid, "Install", estimate_minutes=120)
    assert t1["assignee_name"] and t1["status"] == "new" and t1["phase_id"] == phase_id
    assert t1["ticket_number"] > 0 and t1["blocked"] is False and t1["actual_minutes"] == 0

    dep = admin.post(f"/api/projects/{pid}/tasks/{t2['id']}/dependencies/{t1['id']}")
    assert dep.status_code == 201 and dep.json()["depends_on"] == [t1["id"]]
    assert dep.json()["blocked"] is True
    loop = admin.post(f"/api/projects/{pid}/tasks/{t1['id']}/dependencies/{t2['id']}")
    assert loop.status_code == 409 and "loop" in loop.json()["detail"]

    r = admin.patch(
        f"/api/projects/{pid}/tasks/{t1['id']}",
        json={"title": "Site survey", "status": "resolved", "estimate_minutes": 90},
    )
    assert r.status_code == 200
    assert (r.json()["title"], r.json()["status"], r.json()["estimate_minutes"]) == (
        "Site survey",
        "resolved",
        90,
    )
    got = admin.get(f"/api/projects/{pid}").json()
    assert {t["id"]: t["blocked"] for t in got["tasks"]} == {t1["id"]: False, t2["id"]: False}
    assert got["phases"][0]["task_count"] == 1 and got["task_count"] == 2
    assert got["done_count"] == 1

    ticket = admin.get(f"/api/tickets/{t1['ticket_id']}").json()
    assert ticket["project_id"] == pid and ticket["project_name"] == "Rollout"
    assert ticket["source"] == "project"

    log(t1["ticket_id"], wt["Remote"], 90)
    b = admin.get(f"/api/projects/{pid}/budget")
    assert b.status_code == 200
    assert b.json() == {
        "estimate_minutes": 210,
        "actual_minutes": 90,
        "billable_minutes": 90,
        "cost_at_rates_cents": 22_500,
        "billed_cents": 0,
        "remaining_cents": 50_000,
        "over_budget": False,
    }
    assert admin.get(f"/api/projects/{pid}").json()["budget"] == b.json()

    approved = admin.post(f"/api/projects/{pid}/approve")
    assert approved.status_code == 200 and approved.json()["status"] == "active"
    assert (
        admin.patch(f"/api/projects/{pid}", json={"billing_mode": "fixed_fee"}).status_code == 409
    )
    assert admin.patch(f"/api/projects/{pid}", json={"budget_cents": 60_000}).status_code == 200
    assert admin.patch(f"/api/projects/{pid}", json={"name": "Rollout 2"}).json()["name"] == (
        "Rollout 2"
    )

    assert (
        admin.delete(f"/api/projects/{pid}/tasks/{t2['id']}/dependencies/{t1['id']}").status_code
        == 200
    )
    assert admin.delete(f"/api/projects/{pid}/phases/{phase_id}").status_code == 409
    admin.patch(f"/api/projects/{pid}/tasks/{t1['id']}", json={"phase_id": None})
    assert admin.patch(
        f"/api/projects/{pid}/phases/{phase_id}", json={"completed": True, "name": "Planned"}
    ).json()["completed_at"]
    assert admin.delete(f"/api/projects/{pid}/phases/{phase_id}").status_code == 204

    assert admin.post(f"/api/projects/{pid}/status", json={"status": "on_hold"}).status_code == 200
    done = admin.post(f"/api/projects/{pid}/status", json={"status": "active"})
    assert done.json()["status"] == "active"
    admin.post(f"/api/projects/{pid}/status", json={"status": "completed"})
    back = admin.post(f"/api/projects/{pid}/status", json={"status": "active"})
    assert back.status_code == 409


def test_list_and_filters(admin, org, make_org):
    other = make_org("Other")["id"]
    a, b = create(admin, org, name="A"), create(admin, other, name="B")
    assert {p["id"] for p in admin.get("/api/projects").json()} == {a["id"], b["id"]}
    assert [
        p["id"] for p in admin.get("/api/projects", params={"organization_id": org}).json()
    ] == [a["id"]]
    admin.post(f"/api/projects/{b['id']}/status", json={"status": "cancelled"})
    r = admin.get("/api/projects", params={"status": "cancelled"}).json()
    assert [p["id"] for p in r] == [b["id"]] and r[0]["task_count"] == 0
    assert admin.get("/api/projects", params={"status": "bogus"}).status_code == 422


def test_approve_edge_cases_map_to_409(admin, org):
    bare = create(admin, org)
    assert admin.post(f"/api/projects/{bare['id']}/approve").status_code == 409
    no_fee = create(admin, org, billing_mode="fixed_fee")
    assert admin.post(f"/api/projects/{no_fee['id']}/approve").status_code == 409
    ok = create(admin, org, billing_mode="fixed_fee", fixed_fee_cents=99_900, taxable=True)
    done = admin.post(f"/api/projects/{ok['id']}/approve").json()
    assert done["status"] == "active" and done["fixed_fee_cents"] == 99_900 and done["taxable"]
    assert admin.post(f"/api/projects/{ok['id']}/approve").status_code == 409
    assert admin.patch(f"/api/projects/{ok['id']}", json={"fixed_fee_cents": 1}).status_code == 409
    assert admin.patch(f"/api/projects/{ok['id']}", json={"taxable": False}).status_code == 409


def test_validation_errors(admin, org):
    bad = [
        {"organization_id": org, "name": ""},
        {"organization_id": org, "name": "x" * 201},
        {"organization_id": org, "name": "x", "fixed_fee_cents": 0},
        {"organization_id": org, "name": "x", "budget_cents": -5},
        {"organization_id": org, "name": "x", "billing_mode": "retainer"},
    ]
    for body in bad:
        assert admin.post("/api/projects", json=body).status_code == 422, body
    p = create(admin, org)
    pid = p["id"]
    assert (
        admin.post(
            f"/api/projects/{pid}/tasks", json={"title": "x", "estimate_minutes": 1_000_001}
        ).status_code
        == 422
    )
    assert (
        admin.post(
            f"/api/projects/{pid}/tasks", json={"title": "x", "estimate_minutes": -1}
        ).status_code
        == 422
    )
    assert admin.post(f"/api/projects/{pid}/phases", json={"name": ""}).status_code == 422
    assert (
        admin.post("/api/projects", json={"organization_id": 999_999, "name": "x"}).status_code
        == 404
    )


def test_not_found(admin, org):
    pid = create(admin, org)["id"]
    for method, url in (
        ("get", "/api/projects/999999"),
        ("get", "/api/projects/999999/budget"),
        ("post", "/api/projects/999999/approve"),
        ("patch", f"/api/projects/{pid}/phases/999999"),
        ("delete", f"/api/projects/{pid}/phases/999999"),
        ("patch", f"/api/projects/{pid}/tasks/999999"),
        ("post", f"/api/projects/{pid}/tickets/999999"),
        ("delete", f"/api/projects/{pid}/tasks/1/dependencies/2"),
    ):
        kw = {"json": {}} if method == "patch" else {}
        assert getattr(admin, method)(url, **kw).status_code == 404, (method, url)


def test_dependency_rules(admin, org):
    a, b = create(admin, org, name="A"), create(admin, org, name="B")
    ta, ta2, tb = add_task(admin, a["id"]), add_task(admin, a["id"]), add_task(admin, b["id"])
    cross = admin.post(f"/api/projects/{a['id']}/tasks/{ta['id']}/dependencies/{tb['id']}")
    assert cross.status_code == 409
    own = admin.post(f"/api/projects/{a['id']}/tasks/{ta['id']}/dependencies/{ta['id']}")
    assert own.status_code == 409
    # a task that is in another project cannot be reached through this project's URL
    wrong = admin.post(f"/api/projects/{b['id']}/tasks/{ta['id']}/dependencies/{ta2['id']}")
    assert wrong.status_code == 404
    ok = admin.post(f"/api/projects/{a['id']}/tasks/{ta['id']}/dependencies/{ta2['id']}")
    assert ok.status_code == 201
    dup = admin.post(f"/api/projects/{a['id']}/tasks/{ta['id']}/dependencies/{ta2['id']}")
    assert dup.status_code == 409


def test_three_task_cycle_via_api(admin, org):
    pid = create(admin, org)["id"]
    a, b, c = (add_task(admin, pid, n) for n in "ABC")

    def dep(x, y):
        return admin.post(f"/api/projects/{pid}/tasks/{x['id']}/dependencies/{y['id']}")

    assert dep(a, b).status_code == 201 and dep(b, c).status_code == 201
    assert dep(c, a).status_code == 409


def test_attach_and_detach_tickets(admin, org_ctx, make_ticket, make_org_with_ticket):
    pid = create(admin, org_ctx["org"])["id"]
    other = create(admin, org_ctx["org"], name="Other")["id"]
    ticket = make_ticket()
    r = admin.post(f"/api/projects/{pid}/tickets/{ticket['id']}")
    assert r.status_code == 200 and r.json()["project_id"] == pid
    assert r.json()["project_name"] == "Rollout"
    assert admin.post(f"/api/projects/{other}/tickets/{ticket['id']}").status_code == 409
    # the generic ticket PATCH cannot move a ticket between projects
    admin.patch(f"/api/tickets/{ticket['id']}", json={"project_id": other})
    assert admin.get(f"/api/tickets/{ticket['id']}").json()["project_id"] == pid
    _, foreign = make_org_with_ticket("Foreign")
    assert admin.post(f"/api/projects/{pid}/tickets/{foreign['id']}").status_code == 409
    own = add_task(admin, pid)
    assert admin.delete(f"/api/projects/{pid}/tickets/{own['ticket_id']}").status_code == 409
    d = admin.delete(f"/api/projects/{pid}/tickets/{ticket['id']}")
    assert d.status_code == 200 and d.json()["project_id"] is None
    assert admin.delete(f"/api/projects/{pid}/tickets/{ticket['id']}").status_code == 409


def test_tech_can_work_but_not_bill(tech, admin, org):
    p = create(tech, org)
    pid = p["id"]
    assert p["billing_mode"] is None
    for body in (
        {"billing_mode": "tm"},
        {"fixed_fee_cents": 100},
        {"budget_cents": 100},
        {"taxable": True},
    ):
        r = tech.post("/api/projects", json={"organization_id": org, "name": "x", **body})
        assert r.status_code == 403 and r.json()["detail"] == "Not permitted", body
        assert tech.patch(f"/api/projects/{pid}", json=body).status_code == 403
    assert tech.patch(f"/api/projects/{pid}", json={"name": "Mine"}).status_code == 200
    ph = tech.post(f"/api/projects/{pid}/phases", json={"name": "P"}).json()
    t = add_task(tech, pid, phase_id=ph["id"])
    assert (
        tech.patch(f"/api/projects/{pid}/tasks/{t['id']}", json={"status": "open"}).status_code
        == 200
    )
    assert tech.get(f"/api/projects/{pid}/budget").status_code == 200
    assert tech.post(f"/api/projects/{pid}/approve").status_code == 403
    admin.patch(f"/api/projects/{pid}", json={"billing_mode": "tm", "budget_cents": 1000})
    assert tech.post(f"/api/projects/{pid}/approve").status_code == 403
    assert tech.post(f"/api/projects/{pid}/status", json={"status": "cancelled"}).status_code == 200


def test_billing_role_approves_but_cannot_write_projects(biller, admin, org):
    pid = create(admin, org, billing_mode="tm", budget_cents=1000)["id"]
    assert biller.get(f"/api/projects/{pid}").status_code == 200
    assert (
        biller.post("/api/projects", json={"organization_id": org, "name": "x"}).status_code == 403
    )
    assert biller.post(f"/api/projects/{pid}/approve").status_code == 200


def test_read_only_can_read_but_not_write(read_only, admin, org):
    pid = create(admin, org)["id"]
    t = add_task(admin, pid)
    t2 = add_task(admin, pid)
    ph = admin.post(f"/api/projects/{pid}/phases", json={"name": "P"}).json()
    assert read_only.get("/api/projects").status_code == 200
    assert read_only.get(f"/api/projects/{pid}").status_code == 200
    assert read_only.get(f"/api/projects/{pid}/budget").status_code == 200
    writes = (
        ("post", "/api/projects", {"organization_id": org, "name": "x"}),
        ("patch", f"/api/projects/{pid}", {"name": "x"}),
        ("post", f"/api/projects/{pid}/approve", None),
        ("post", f"/api/projects/{pid}/status", {"status": "cancelled"}),
        ("post", f"/api/projects/{pid}/phases", {"name": "x"}),
        ("patch", f"/api/projects/{pid}/phases/{ph['id']}", {"name": "x"}),
        ("delete", f"/api/projects/{pid}/phases/{ph['id']}", None),
        ("post", f"/api/projects/{pid}/tasks", {"title": "x"}),
        ("patch", f"/api/projects/{pid}/tasks/{t['id']}", {"title": "x"}),
        ("post", f"/api/projects/{pid}/tasks/{t['id']}/dependencies/{t2['id']}", None),
        ("delete", f"/api/projects/{pid}/tasks/{t['id']}/dependencies/{t2['id']}", None),
        ("post", f"/api/projects/{pid}/tickets/{t['ticket_id']}", None),
        ("delete", f"/api/projects/{pid}/tickets/{t['ticket_id']}", None),
    )
    for method, url, body in writes:
        kw = {"json": body} if body is not None else {}
        assert getattr(read_only, method)(url, **kw).status_code == 403, (method, url)


def test_anonymous_is_refused(anon):
    assert anon.get("/api/projects").status_code == 401
    assert anon.get("/api/projects/1/budget").status_code == 401


def test_closed_project_takes_no_new_tasks(admin, org):
    pid = create(admin, org)["id"]
    admin.post(f"/api/projects/{pid}/status", json={"status": "cancelled"})
    assert admin.post(f"/api/projects/{pid}/tasks", json={"title": "x"}).status_code == 409
    assert admin.post(f"/api/projects/{pid}/phases", json={"name": "x"}).status_code == 409
