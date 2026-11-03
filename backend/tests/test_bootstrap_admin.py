import pytest
from sqlalchemy import text

from app import bootstrap_admin


def users(owner):
    return owner.execute(text("SELECT email, display_name, role, is_active FROM users")).all()


def audits(owner):
    return owner.execute(
        text(
            "SELECT actor_type, actor_id, detail FROM audit_log"
            " WHERE action = 'auth.bootstrap_admin'"
        )
    ).all()


def test_creates_once_and_is_idempotent(owner, monkeypatch, login):
    monkeypatch.setenv("BOOTSTRAP_ADMIN_EMAIL", "Owner@msp.example.com")
    assert bootstrap_admin.run() == "created"
    assert bootstrap_admin.run() == "unchanged"
    assert users(owner) == [("Owner@msp.example.com", "Owner", "admin", True)]
    assert audits(owner) == [("system", None, {"outcome": "created"})]
    # the row is matched by email the way staff sign-in matches (case-insensitive)
    assert login("admin", "owner@msp.example.com").get("/api/v1/auth/me").json()["role"] == "admin"


def test_existing_tech_promoted_and_reactivated(owner, make_user, monkeypatch):
    make_user("tech", "lead@msp.example.com", active=False)
    monkeypatch.setenv("BOOTSTRAP_ADMIN_EMAIL", "lead@msp.example.com")
    assert bootstrap_admin.run() == "promoted"
    assert users(owner) == [("lead@msp.example.com", "tech user", "admin", True)]
    assert audits(owner) == [("system", None, {"outcome": "promoted"})]


@pytest.mark.parametrize("value", ["", "  ", "unset"])
def test_empty_env_is_a_noop(owner, monkeypatch, value):
    monkeypatch.setenv("BOOTSTRAP_ADMIN_EMAIL", value)
    assert bootstrap_admin.run() == "skipped"
    assert users(owner) == [] and audits(owner) == []


def test_invalid_email_refused(owner, monkeypatch):
    monkeypatch.setenv("BOOTSTRAP_ADMIN_EMAIL", "not-an-email")
    with pytest.raises(SystemExit):
        bootstrap_admin.run()
    assert users(owner) == []
