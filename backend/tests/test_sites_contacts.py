def test_site_crud_and_audit(admin, make_org):
    org = make_org()
    r = admin.post(f"/api/organizations/{org['id']}/sites", json={"name": "HQ", "city": "Austin"})
    assert r.status_code == 201
    site = r.json()
    assert site["organization_id"] == org["id"]

    r = admin.patch(f"/api/sites/{site['id']}", json={"city": "Dallas"})
    assert r.json()["city"] == "Dallas" and r.json()["name"] == "HQ"

    assert admin.post(f"/api/sites/{site['id']}/archive").json()["archived_at"]
    assert admin.get(f"/api/organizations/{org['id']}/sites").json() == []
    assert (
        len(
            admin.get(
                f"/api/organizations/{org['id']}/sites", params={"include_archived": True}
            ).json()
        )
        == 1
    )
    assert admin.post(f"/api/sites/{site['id']}/unarchive").json()["archived_at"] is None

    actions = [
        a["action"]
        for a in admin.get("/api/audit", params={"entity_type": "sites"}).json()["items"]
    ]
    assert actions == ["site.unarchive", "site.archive", "site.update", "site.create"]


def test_site_404s(admin, make_org):
    assert admin.post("/api/organizations/999/sites", json={"name": "x"}).status_code == 404
    assert admin.get("/api/organizations/999/sites").status_code == 404
    assert admin.patch("/api/sites/999", json={"name": "x"}).status_code == 404
    assert admin.post("/api/sites/999/archive").status_code == 404


def test_contact_crud_and_audit(admin, make_org):
    org = make_org()
    r = admin.post(
        f"/api/organizations/{org['id']}/contacts",
        json={"name": "Pat", "email": "Pat@Acme.com", "is_billing_contact": True},
    )
    assert r.status_code == 201
    contact = r.json()
    r = admin.patch(f"/api/contacts/{contact['id']}", json={"phone": "555-0100"})
    assert r.json()["phone"] == "555-0100" and r.json()["is_billing_contact"] is True
    assert admin.post(f"/api/contacts/{contact['id']}/archive").json()["archived_at"]
    assert admin.get(f"/api/organizations/{org['id']}/contacts").json() == []
    assert admin.post(f"/api/contacts/{contact['id']}/unarchive").status_code == 200
    actions = [
        a["action"]
        for a in admin.get("/api/audit", params={"entity_type": "contacts"}).json()["items"]
    ]
    assert actions == ["contact.unarchive", "contact.archive", "contact.update", "contact.create"]


def test_contact_email_unique_per_org_case_insensitive(admin, make_org):
    a, b = make_org("A"), make_org("B")
    body = {"name": "Pat", "email": "pat@x.com"}
    assert admin.post(f"/api/organizations/{a['id']}/contacts", json=body).status_code == 201
    dup = {"name": "Pat2", "email": "PAT@x.com"}
    assert admin.post(f"/api/organizations/{a['id']}/contacts", json=dup).status_code == 409
    # same email in a different org is fine
    assert admin.post(f"/api/organizations/{b['id']}/contacts", json=body).status_code == 201


def test_only_one_primary_contact_and_promotion_demotes_previous(admin, make_org):
    org = make_org()
    url = f"/api/organizations/{org['id']}/contacts"
    c1 = admin.post(url, json={"name": "One", "is_primary": True}).json()
    c2 = admin.post(url, json={"name": "Two", "is_primary": True}).json()
    contacts = {c["id"]: c for c in admin.get(url).json()}
    assert contacts[c1["id"]]["is_primary"] is False
    assert contacts[c2["id"]]["is_primary"] is True
    admin.patch(f"/api/contacts/{c1['id']}", json={"is_primary": True})
    contacts = {c["id"]: c for c in admin.get(url).json()}
    assert contacts[c1["id"]]["is_primary"] and not contacts[c2["id"]]["is_primary"]
    # the implicit demotion is audited too
    ups = admin.get("/api/audit", params={"entity_id": c2["id"], "entity_type": "contacts"}).json()[
        "items"
    ]
    assert any(a["before"]["is_primary"] and not a["after"]["is_primary"] for a in ups)


def test_contact_site_must_belong_to_same_org(admin, make_org):
    a, b = make_org("A"), make_org("B")
    site_b = admin.post(f"/api/organizations/{b['id']}/sites", json={"name": "B HQ"}).json()
    r = admin.post(
        f"/api/organizations/{a['id']}/contacts", json={"name": "Pat", "site_id": site_b["id"]}
    )
    assert r.status_code == 409
    site_a = admin.post(f"/api/organizations/{a['id']}/sites", json={"name": "A HQ"}).json()
    r = admin.post(
        f"/api/organizations/{a['id']}/contacts", json={"name": "Pat", "site_id": site_a["id"]}
    )
    assert r.status_code == 201


def test_contact_validation_and_404(admin, make_org):
    org = make_org()
    url = f"/api/organizations/{org['id']}/contacts"
    assert admin.post(url, json={"name": "x", "email": "not-an-email"}).status_code == 422
    assert admin.post("/api/organizations/999/contacts", json={"name": "x"}).status_code == 404
    assert admin.get("/api/organizations/999/contacts").status_code == 404
    assert admin.patch("/api/contacts/999", json={"name": "x"}).status_code == 404
    assert admin.post("/api/contacts/999/archive").status_code == 404
    assert admin.post("/api/contacts/999/unarchive").status_code == 404
    assert admin.post("/api/sites/999/unarchive").status_code == 404
    assert admin.post("/api/organizations/999/unarchive").status_code == 404
