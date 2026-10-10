def audit_actions(admin, **params):
    return [a["action"] for a in admin.get("/api/audit", params=params).json()["items"]]


def test_create_get_update_archive(admin, make_org):
    org = make_org("Acme Corp", notes="hi")
    assert org["status"] == "active" and org["archived_at"] is None
    assert admin.get(f"/api/organizations/{org['id']}").json()["name"] == "Acme Corp"

    r = admin.patch(
        f"/api/organizations/{org['id']}", json={"name": "Acme Inc", "status": "inactive"}
    )
    assert r.status_code == 200
    assert r.json()["name"] == "Acme Inc" and r.json()["status"] == "inactive"
    assert r.json()["notes"] == "hi"  # untouched fields survive a PATCH

    assert admin.post(f"/api/organizations/{org['id']}/archive").json()["archived_at"]
    assert admin.get("/api/organizations").json()["total"] == 0
    assert admin.get("/api/organizations", params={"include_archived": True}).json()["total"] == 1
    assert admin.post(f"/api/organizations/{org['id']}/unarchive").json()["archived_at"] is None
    assert admin.get("/api/organizations").json()["total"] == 1


def test_writes_are_audited_with_before_after(admin, make_org):
    org = make_org("Acme Corp")
    admin.patch(f"/api/organizations/{org['id']}", json={"name": "Acme Inc"})
    admin.post(f"/api/organizations/{org['id']}/archive")
    items = admin.get("/api/audit", params={"entity_type": "organizations"}).json()["items"]
    assert [i["action"] for i in items] == [
        "organization.archive",
        "organization.update",
        "organization.create",
    ]
    update = items[1]
    assert update["before"]["name"] == "Acme Corp" and update["after"]["name"] == "Acme Inc"
    assert update["organization_id"] == org["id"] and update["actor_id"] == admin.user["id"]
    assert update["request_id"]


def test_duplicate_name_conflicts_case_insensitive_but_archived_can_be_reused(admin, make_org):
    org = make_org("Acme Corp")
    assert admin.post("/api/organizations", json={"name": "ACME corp"}).status_code == 409
    admin.post(f"/api/organizations/{org['id']}/archive")
    assert admin.post("/api/organizations", json={"name": "Acme Corp"}).status_code == 201


def test_failed_write_leaves_no_audit_row(admin, make_org):
    make_org("Acme Corp")
    admin.post("/api/organizations", json={"name": "Acme Corp"})
    creates = audit_actions(admin, action="organization.create")
    assert len(creates) == 1


def test_search_and_pagination(admin, make_org):
    for n in ("Alpha", "Beta", "Gamma", "Alphabet"):
        make_org(n)
    r = admin.get("/api/organizations", params={"q": "alpha"}).json()
    assert r["total"] == 2
    page = admin.get("/api/organizations", params={"limit": 2, "offset": 2}).json()
    assert page["total"] == 4 and len(page["items"]) == 2


def test_validation_and_404(admin):
    assert admin.post("/api/organizations", json={"name": ""}).status_code == 422
    assert admin.get("/api/organizations/999").status_code == 404
    assert admin.patch("/api/organizations/999", json={"name": "x"}).status_code == 404
    assert admin.post("/api/organizations/999/archive").status_code == 404
    assert admin.get("/api/organizations", params={"limit": 0}).status_code == 422
