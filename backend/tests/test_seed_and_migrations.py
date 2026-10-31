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
    assert owner.execute(text("SELECT count(*) FROM tickets")).scalar_one() == 12
    tech = login("tech", "tech@example.com")
    assert tech.get("/api/v1/organizations").json()["total"] == 3
    d = tech.get("/api/v1/dashboard").json()
    assert d["counts"]["open"] == 12 and d["counts"]["needs_triage"] == 1
    assert len(d["my_open"]) == 6
    assert owner.execute(text("SELECT count(*) FROM agreements")).scalar_one() == 4
    assert owner.execute(text("SELECT count(*) FROM product_charges")).scalar_one() == 1
    assert owner.execute(text("SELECT count(*) FROM assets")).scalar_one() == 5
    biller = login("billing", "billing@example.com")
    r = biller.post("/api/v1/billing-runs", json={"period": biz_today().strftime("%Y-%m")})
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


def test_migration_0032_reporting_tables_and_constraints(owner_engine, make_user):
    from sqlalchemy.exc import IntegrityError

    with owner_engine.connect() as c:
        assert c.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "0033"
    uid = make_user("admin")["id"]

    def schedule(**kw):
        row = {
            "n": "Weekly SLA",
            "r": "sla",
            "f": "weekly",
            "wd": 0,
            "dom": None,
            "ids": [uid],
            **kw,
        }
        with owner_engine.begin() as c:
            c.execute(
                text(
                    "INSERT INTO report_schedules (name, report, frequency, weekday, day_of_month,"
                    " recipient_user_ids) VALUES (:n, :r, :f, :wd, :dom, :ids)"
                ),
                row,
            )

    schedule()
    for bad in (
        dict(r="other"),
        dict(f="daily"),
        dict(wd=7),
        dict(wd=None),  # weekly needs a weekday
        dict(dom=5),  # and no day of month
        dict(f="monthly", wd=None, dom=29),
        dict(ids=[]),
        dict(ids=list(range(1, 22))),
    ):
        with pytest.raises(IntegrityError):
            schedule(**bad)
    schedule(f="monthly", wd=None, dom=28)
    with owner_engine.begin() as c:
        sid = c.execute(text("SELECT id FROM report_schedules ORDER BY id LIMIT 1")).scalar_one()
        run = "INSERT INTO report_schedule_runs (schedule_id, period_start, period_end, status)"
        c.execute(text(run + " VALUES (:s, '2026-03-02', '2026-03-08', 'sent')"), dict(s=sid))
    with pytest.raises(IntegrityError), owner_engine.begin() as c:  # one run per period
        c.execute(text(run + " VALUES (:s, '2026-03-02', '2026-03-08', 'failed')"), dict(s=sid))
    with pytest.raises(IntegrityError), owner_engine.begin() as c:
        c.execute(text("UPDATE users SET cost_rate_cents = -1 WHERE id = :u"), dict(u=uid))
    with owner_engine.connect() as c:
        for table in ("report_schedules", "report_schedule_runs"):
            granted = {
                p: c.execute(
                    text("SELECT has_table_privilege('psa_app', :t, :p)"), dict(t=table, p=p)
                ).scalar_one()
                for p in ("SELECT", "INSERT", "UPDATE", "DELETE")
            }
            assert granted == {"SELECT": True, "INSERT": True, "UPDATE": True, "DELETE": False}
