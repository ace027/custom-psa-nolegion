from types import SimpleNamespace

from app import audit_text as t


def entry(**kw):
    base = dict(
        actor_type="user",
        actor_id=7,
        action="organization.create",
        entity_type="organizations",
        entity_id=3,
    )
    return SimpleNamespace(**{**base, **kw})


def test_record_label():
    assert t.record_label("time_entries") == "time entry"
    assert t.record_label("organizations") == "client"
    assert t.record_label("categories") == "category"
    assert t.record_label("addresses") == "address"
    assert t.record_label("service_queues") == "service queue"


def test_summary_variants():
    assert t.summary(entry(), "Ann", "Acme") == "Ann created client #3 for Acme"
    assert t.summary(entry(), None, None) == "User #7 created client #3"
    assert t.summary(entry(actor_type="system"), None, None).startswith("System ")
    assert t.summary(entry(actor_type="anonymous"), None, None).startswith("Someone (not")
    assert "wibble the" in t.summary(entry(action="x.wibble_the"), "A", None)
    e = entry(action="auth.login", entity_type=None, entity_id=None)
    assert t.summary(e, "Ann", None) == "Ann signed in (auth)"


def test_changes_rules():
    out = t.changes(
        {"id": 1, "name": "a", "rate_cents": 123456, "billable": False, "x": None, "same": 1},
        {
            "id": 2,
            "name": "b",
            "rate_cents": 150000,
            "billable": True,
            "x": [1, 2],
            "same": 1,
            "updated_at": "z",
        },
    )
    by = {c["field"]: c for c in out}
    assert [c["field"] for c in out] == sorted(by)
    assert set(by) == {"name", "rate_cents", "billable", "x"}
    assert by["rate_cents"]["label"] == "rate"
    assert (by["rate_cents"]["before"], by["rate_cents"]["after"]) == ("1,234.56", "1,500.00")
    assert (by["billable"]["before"], by["billable"]["after"]) == ("no", "yes")
    assert (by["x"]["before"], by["x"]["after"]) == ("(empty)", "[1,2]")


def test_changes_minutes_secret_long_and_empty():
    out = t.changes({"budget_minutes": 90}, {"budget_minutes": 150})
    assert (out[0]["before"], out[0]["after"]) == ("1 h 30 min", "2 h 30 min")
    out = t.changes({"api_secret": "a"}, {"api_secret": "b"})
    assert (out[0]["before"], out[0]["after"]) == ("(changed)", "(changed)")
    assert len(t.changes(None, {"n": "x" * 500})[0]["after"]) == 200
    assert t.changes(None, None) == []
