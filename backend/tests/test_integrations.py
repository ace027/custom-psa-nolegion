"""Connecting vendors: credentials are encrypted and write-only, mapping never guesses."""

import pytest
from sqlalchemy import text

from app import crypto
from tests.vendorfakes import HUDU, NINJA, dev, run_sync, vendors  # noqa: F401


def connect(admin, body=NINJA):
    r = admin.post("/api/integrations", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_credentials_are_encrypted_at_rest_and_never_returned(admin, owner):
    i = connect(admin)
    assert i["credentials_set"] is True
    assert "super-secret-value" not in str(i) and "cid-123" not in str(i)
    stored = owner.execute(text("SELECT credentials FROM integrations")).scalar()
    assert "super-secret-value" not in stored and "cid-123" not in stored
    assert crypto.decrypt_credentials(stored)["client_secret"] == "super-secret-value"
    for r in (admin.get("/api/integrations"), admin.get(f"/api/integrations/{i['id']}/runs")):
        assert "super-secret-value" not in r.text


def test_secrets_never_reach_the_audit_log(admin, owner):
    i = connect(admin)
    admin.patch(
        f"/api/integrations/{i['id']}",
        json={"credentials": {"client_id": "new-id-999", "client_secret": "rotated-secret-777"}},
    )
    dump = str(owner.execute(text("SELECT before, after, detail FROM audit_log")).all())
    for secret in ("super-secret-value", "cid-123", "rotated-secret-777", "new-id-999"):
        assert secret not in dump
    actions = [r[0] for r in owner.execute(text("SELECT action FROM audit_log"))]
    assert "integration.created" in actions and "integration.credentials_changed" in actions


def test_replacing_credentials_overwrites_the_old_value(admin, owner):
    i = connect(admin)
    admin.patch(
        f"/api/integrations/{i['id']}",
        json={"credentials": {"client_id": "b", "client_secret": "second"}},
    )
    stored = owner.execute(text("SELECT credentials FROM integrations")).scalar()
    assert crypto.decrypt_credentials(stored) == {"client_id": "b", "client_secret": "second"}


def test_incomplete_credentials_are_refused(admin):
    r = admin.post("/api/integrations", json={**NINJA, "credentials": {"client_id": "x"}})
    assert r.status_code == 409


def test_vendor_url_must_be_https(admin):
    r = admin.post("/api/integrations", json={**NINJA, "base_url": "http://app.ninjarmm.com"})
    assert r.status_code == 422


def test_hudu_layout_config_is_validated(admin):
    r = admin.post("/api/integrations", json={**HUDU, "config": {"layouts": {"Switches": "gizmo"}}})
    assert r.status_code == 409


def test_missing_key_is_a_clear_error_not_a_crash(admin, monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("CREDENTIALS_KEY", "")
    get_settings.cache_clear()
    try:
        r = admin.post("/api/integrations", json=NINJA)
        assert r.status_code == 409 and "CREDENTIALS_KEY" in r.json()["detail"]
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()


def test_key_rotation_decrypts_with_old_key_and_reencrypts(monkeypatch):
    from cryptography.fernet import Fernet

    from app.config import get_settings

    old = get_settings().credentials_key
    new = Fernet.generate_key().decode()
    token = crypto.encrypt_credentials({"k": "v"})
    monkeypatch.setenv("CREDENTIALS_KEY", f"{new},{old}")
    get_settings.cache_clear()
    try:
        assert crypto.decrypt_credentials(token) == {"k": "v"}
        rotated = crypto.reencrypt(token)
        monkeypatch.setenv("CREDENTIALS_KEY", new)
        get_settings.cache_clear()
        assert crypto.decrypt_credentials(rotated) == {"k": "v"}  # old key no longer needed
        with pytest.raises(crypto.CredentialsKeyError):
            crypto.decrypt_credentials(token)
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()


def test_test_connection_reports_ok_and_failure(admin, vendors):  # noqa: F811
    i = connect(admin)
    assert admin.post(f"/api/integrations/{i['id']}/test").json() == {"ok": True, "error": None}
    vendors[i["id"]].fail_test = True
    r = admin.post(f"/api/integrations/{i['id']}/test").json()
    assert r["ok"] is False and "401" in r["error"]
    assert admin.get("/api/integrations").json()[0]["status"] == "error"


def test_clients_start_unmapped_with_name_suggestions_never_applied(
    admin,
    make_org,
    vendors,  # noqa: F811
):
    acme = make_org("Acme Corp")
    i = connect(admin)
    vendors[i["id"]].clients = {"7": "acme corp", "8": "Globex"}
    rows = admin.post(f"/api/integrations/{i['id']}/clients/refresh").json()
    by = {r["external_name"]: r for r in rows}
    assert by["acme corp"]["suggested_organization_id"] == acme["id"]
    assert by["acme corp"]["organization_id"] is None  # suggested, never guessed
    assert by["acme corp"]["needs_mapping"] and by["Globex"]["needs_mapping"]
    assert by["Globex"]["suggested_organization_id"] is None


def test_map_and_ignore_a_vendor_client(admin, make_org, vendors):  # noqa: F811
    acme = make_org("Acme Corp")
    i = connect(admin)
    vendors[i["id"]].clients = {"7": "Acme", "8": "Globex"}
    rows = admin.post(f"/api/integrations/{i['id']}/clients/refresh").json()
    a, g = rows[0], rows[1]
    r = admin.put(
        f"/api/integrations/{i['id']}/clients/{a['id']}", json={"organization_id": acme["id"]}
    )
    assert r.status_code == 200 and r.json()["needs_mapping"] is False
    r = admin.put(f"/api/integrations/{i['id']}/clients/{g['id']}", json={"ignored": True})
    assert r.json()["ignored"] and not r.json()["needs_mapping"]
    both = admin.put(
        f"/api/integrations/{i['id']}/clients/{g['id']}",
        json={"organization_id": acme["id"], "ignored": True},
    )
    assert both.status_code == 409
    nope = admin.put(
        f"/api/integrations/{i['id']}/clients/{g['id']}", json={"organization_id": 999}
    )
    assert nope.status_code == 404


def test_sync_now_only_flags_the_request_for_the_worker(admin, vendors):  # noqa: F811
    i = connect(admin)
    assert admin.post(f"/api/integrations/{i['id']}/sync").json()["sync_requested"] is True
    admin.patch(f"/api/integrations/{i['id']}", json={"enabled": False})
    assert admin.post(f"/api/integrations/{i['id']}/sync").status_code == 409


def test_only_admins_manage_integrations(login, admin):
    i = connect(admin)
    for role in ("tech", "billing", "read_only"):
        c = login(role)
        assert c.get("/api/integrations").status_code == 403
        assert c.post("/api/integrations", json=NINJA).status_code == 403
        assert c.patch(f"/api/integrations/{i['id']}", json={"enabled": False}).status_code == 403
        assert c.post(f"/api/integrations/{i['id']}/test").status_code == 403
        assert c.get(f"/api/integrations/{i['id']}/clients").status_code == 403


def test_unknown_integration_is_404(admin):
    assert admin.post("/api/integrations/999/test").status_code == 404
    assert admin.get("/api/integrations/999/runs").status_code == 404
    assert admin.get("/api/integrations/999/clients").status_code == 404


def test_rekey_job_reencrypts_every_stored_credential(admin, owner, monkeypatch):
    from cryptography.fernet import Fernet

    from app import rekey
    from app.config import get_settings

    connect(admin)
    old = get_settings().credentials_key
    new = Fernet.generate_key().decode()
    monkeypatch.setenv("CREDENTIALS_KEY", f"{new},{old}")
    get_settings.cache_clear()
    try:
        assert rekey.main() == 0
        monkeypatch.setenv("CREDENTIALS_KEY", new)  # the old key is no longer needed
        get_settings.cache_clear()
        stored = owner.execute(text("SELECT credentials FROM integrations")).scalar()
        assert crypto.decrypt_credentials(stored)["client_secret"] == "super-secret-value"
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()
