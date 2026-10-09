def test_admin_can_provision_list_and_update_users(admin):
    r = admin.post(
        "/api/users", json={"email": "New@Example.com", "display_name": "New Tech", "role": "tech"}
    )
    assert r.status_code == 201 and r.json()["role"] == "tech" and r.json()["is_active"]
    uid = r.json()["id"]
    assert {u["email"] for u in admin.get("/api/users").json()} >= {"New@example.com"}
    r = admin.patch(f"/api/users/{uid}", json={"role": "billing", "display_name": "N"})
    assert r.json()["role"] == "billing" and r.json()["display_name"] == "N"


def test_duplicate_email_conflicts_case_insensitive(admin):
    body = {"email": "x@example.com", "display_name": "X", "role": "tech"}
    assert admin.post("/api/users", json=body).status_code == 201
    assert admin.post("/api/users", json={**body, "email": "X@EXAMPLE.com"}).status_code == 409


def test_invalid_role_rejected(admin):
    r = admin.post(
        "/api/users", json={"email": "x@example.com", "display_name": "X", "role": "root"}
    )
    assert r.status_code == 422


def test_cannot_demote_or_deactivate_self(admin):
    me = admin.user["id"]
    assert admin.patch(f"/api/users/{me}", json={"role": "tech"}).status_code == 403
    assert admin.patch(f"/api/users/{me}", json={"is_active": False}).status_code == 403
    assert admin.patch(f"/api/users/{me}", json={"display_name": "Renamed"}).status_code == 200


def test_role_change_and_deactivation_are_audited_and_revoke_sessions(admin, login):
    tech = login("tech")
    assert tech.get("/api/auth/me").status_code == 200
    tid = tech.user["id"]
    admin.patch(f"/api/users/{tid}", json={"role": "read_only"})
    assert tech.post("/api/organizations", json={"name": "x"}).status_code == 403  # immediate

    admin.patch(f"/api/users/{tid}", json={"is_active": False})
    assert tech.get("/api/auth/me").status_code == 401  # sessions killed
    actions = [
        a["action"] for a in admin.get("/api/audit", params={"action": "auth."}).json()["items"]
    ]
    assert "auth.role_changed" in actions and "auth.sessions_revoked" in actions


def test_update_unknown_user_404(admin):
    assert admin.patch("/api/users/999", json={"role": "tech"}).status_code == 404
