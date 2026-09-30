import pytest
from alembic.config import Config
from sqlalchemy import text

from alembic import command
from app import seed


def test_seed_is_idempotent_and_usable(login, owner):
    seed.run()
    seed.run()
    assert owner.execute(text("SELECT count(*) FROM organizations")).scalar_one() == 3
    assert owner.execute(text("SELECT count(*) FROM users")).scalar_one() == 4
    tech = login("tech", "tech@example.com")
    assert tech.get("/api/organizations").json()["total"] == 3


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
