import pytest
from alembic.config import Config
from sqlalchemy import text

from alembic import command
from app import seed
from tests.conftest import biz_today


def test_seed_is_idempotent_and_usable(login, owner):
    seed.run()
    seed.run()
    assert owner.execute(text("SELECT count(*) FROM organizations")).scalar_one() == 3
    assert owner.execute(text("SELECT count(*) FROM users")).scalar_one() == 4
    assert owner.execute(text("SELECT count(*) FROM tickets")).scalar_one() == 5
    tech = login("tech", "tech@example.com")
    assert tech.get("/api/organizations").json()["total"] == 3
    d = tech.get("/api/dashboard").json()
    assert d["counts"]["open"] == 5 and d["counts"]["needs_triage"] == 1
    assert len(d["my_open"]) == 2
    assert owner.execute(text("SELECT count(*) FROM agreements")).scalar_one() == 4
    assert owner.execute(text("SELECT count(*) FROM product_charges")).scalar_one() == 1
    assert owner.execute(text("SELECT count(*) FROM assets")).scalar_one() == 5
    biller = login("billing", "billing@example.com")
    r = biller.post("/api/billing-runs", json={"period": biz_today().strftime("%Y-%m")})
    assert r.status_code == 201 and r.json()["invoice_count"] >= 3


def test_seed_refuses_production(monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "environment", "production")
    with pytest.raises(SystemExit):
        seed.run()


def test_migration_downgrade_and_upgrade_round_trip(owner_engine):
    cfg = Config("alembic.ini")
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    with owner_engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM organizations")).scalar_one() == 0
