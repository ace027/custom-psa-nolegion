def audit_actions(admin, **params):
    return [a["action"] for a in admin.get("/api/v1/audit", params=params).json()["items"]]


def test_create_get_update_archive(admin, make_org):
    org = make_org("Acme Corp", notes="hi")
    assert org["status"] == "active" and org["archived_at"] is None
    assert admin.get(f"/api/v1/organizations/{org['id']}").json()["name"] == "Acme Corp"

    r = admin.patch(
        f"/api/v1/organizations/{org['id']}", json={"name": "Acme Inc", "status": "inactive"}
    )
    assert r.status_code == 200
    assert r.json()["name"] == "Acme Inc" and r.json()["status"] == "inactive"
    assert r.json()["notes"] == "hi"  # untouched fields survive a PATCH

    assert admin.post(f"/api/v1/organizations/{org['id']}/archive").json()["archived_at"]
    assert admin.get("/api/v1/organizations").json()["total"] == 0
    assert (
        admin.get("/api/v1/organizations", params={"include_archived": True}).json()["total"] == 1
    )
    assert admin.post(f"/api/v1/organizations/{org['id']}/unarchive").json()["archived_at"] is None
    assert admin.get("/api/v1/organizations").json()["total"] == 1


def test_writes_are_audited_with_before_after(admin, make_org):
    org = make_org("Acme Corp")
    admin.patch(f"/api/v1/organizations/{org['id']}", json={"name": "Acme Inc"})
    admin.post(f"/api/v1/organizations/{org['id']}/archive")
    items = admin.get("/api/v1/audit", params={"entity_type": "organizations"}).json()["items"]
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
    assert admin.post("/api/v1/organizations", json={"name": "ACME corp"}).status_code == 409
    admin.post(f"/api/v1/organizations/{org['id']}/archive")
    assert admin.post("/api/v1/organizations", json={"name": "Acme Corp"}).status_code == 201


def test_failed_write_leaves_no_audit_row(admin, make_org):
    make_org("Acme Corp")
    admin.post("/api/v1/organizations", json={"name": "Acme Corp"})
    creates = audit_actions(admin, action="organization.create")
    assert len(creates) == 1


def test_search_and_pagination(admin, make_org):
    for n in ("Alpha", "Beta", "Gamma", "Alphabet"):
        make_org(n)
    r = admin.get("/api/v1/organizations", params={"q": "alpha"}).json()
    assert r["total"] == 2
    page = admin.get("/api/v1/organizations", params={"limit": 2, "offset": 2}).json()
    assert page["total"] == 4 and len(page["items"]) == 2


def test_validation_and_404(admin):
    assert admin.post("/api/v1/organizations", json={"name": ""}).status_code == 422
    assert admin.get("/api/v1/organizations/999").status_code == 404
    assert admin.patch("/api/v1/organizations/999", json={"name": "x"}).status_code == 404
    assert admin.post("/api/v1/organizations/999/archive").status_code == 404
    assert admin.get("/api/v1/organizations", params={"limit": 0}).status_code == 422


# ---- Entra tenant id for portal SSO ----
TENANT = "0F1E2D3C-4B5A-6978-8796-A5B4C3D2E1F0"


def test_entra_tenant_id_is_validated_stored_lower_case_and_unique(admin, make_org):
    a, b = make_org("Acme Corp"), make_org("Beta LLC")
    assert a["entra_tenant_id"] is None
    for bad in ("not-a-guid", "0f1e2d3c4b5a69788796a5b4c3d2e1f0", TENANT + "0", "{" + TENANT + "}"):
        r = admin.patch(f"/api/v1/organizations/{a['id']}", json={"entra_tenant_id": bad})
        assert r.status_code == 422, bad
    r = admin.patch(f"/api/v1/organizations/{a['id']}", json={"entra_tenant_id": f" {TENANT} "})
    assert r.status_code == 200 and r.json()["entra_tenant_id"] == TENANT.lower()
    r = admin.patch(f"/api/v1/organizations/{b['id']}", json={"entra_tenant_id": TENANT.lower()})
    assert r.status_code == 409 and "tenant" in r.json()["detail"]
    r = admin.post("/api/v1/organizations", json={"name": "Gamma", "entra_tenant_id": TENANT})
    assert r.status_code == 409
    audit = admin.get("/api/v1/audit", params={"action": "organization.update"}).json()["items"]
    assert audit[0]["after"]["entra_tenant_id"] == TENANT.lower()
    r = admin.patch(f"/api/v1/organizations/{a['id']}", json={"entra_tenant_id": ""})
    assert r.status_code == 200 and r.json()["entra_tenant_id"] is None
    assert admin.patch(
        f"/api/v1/organizations/{b['id']}", json={"entra_tenant_id": TENANT}
    ).is_success  # free again once cleared


def test_only_portal_admins_set_the_tenant_id(admin, make_org, login):
    org = make_org("Acme Corp")
    tech = login("tech", "tech@example.com")
    url = f"/api/v1/organizations/{org['id']}"
    assert tech.patch(url, json={"entra_tenant_id": TENANT}).status_code == 403
    r = tech.post("/api/v1/organizations", json={"name": "Beta", "entra_tenant_id": TENANT})
    assert r.status_code == 403
    assert admin.patch(url, json={"entra_tenant_id": TENANT}).status_code == 200
    assert tech.patch(url, json={"name": "Acme Inc"}).status_code == 200  # other edits still fine
    assert tech.patch(url, json={"entra_tenant_id": None}).json()["entra_tenant_id"] is None


def test_contact_entra_link_flag_and_unlink(admin, make_org, owner):
    from sqlalchemy import text

    org = make_org("Acme Corp")
    c = admin.post(
        f"/api/v1/organizations/{org['id']}/contacts", json={"name": "Pat", "email": "p@a.com"}
    ).json()
    assert c["entra_linked"] is False and "entra_oid" not in c
    owner.execute(text("UPDATE contacts SET entra_oid = 'oid-1' WHERE id = :i"), {"i": c["id"]})
    listed = admin.get(f"/api/v1/organizations/{org['id']}/contacts").json()
    assert listed[0]["entra_linked"] is True
    r = admin.patch(f"/api/v1/contacts/{c['id']}", json={"unlink_entra": True})
    assert r.status_code == 200 and r.json()["entra_linked"] is False
    r = admin.patch(f"/api/v1/contacts/{c['id']}", json={"unlink_entra": True})
    assert r.status_code == 200  # unlinking an unlinked contact is a no-op
