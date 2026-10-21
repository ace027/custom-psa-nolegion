"""CRM schema guards (migration 0030): privileges, forced RLS, CHECKs, cross-client composite FKs,
seeded stages, reminder uniqueness and the renewal settings columns."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db import new_session, set_org_scope

SCOPED = ("opportunities", "renewal_reminders")
ALL = ("leads", "opportunity_stages", *SCOPED)


@pytest.fixture
def two_orgs(make_org):
    return make_org("Org A")["id"], make_org("Org B")["id"]


def stage(owner, kind="open"):
    return owner.execute(
        text("SELECT min(id) FROM opportunity_stages WHERE kind = :k AND active"), {"k": kind}
    ).scalar_one()


def add_agreement(owner, org, name="MSP"):
    return owner.execute(
        text(
            "INSERT INTO agreements (organization_id, name, type, unit_price_cents, start_date) "
            "VALUES (:o, :n, 'flat', 10000, '2026-01-01') RETURNING id"
        ),
        {"o": org, "n": name},
    ).scalar_one()


def add_quote(owner, org):
    survey = owner.execute(
        text("INSERT INTO site_surveys (organization_id) VALUES (:o) RETURNING id"), {"o": org}
    ).scalar_one()
    return owner.execute(
        text(
            "INSERT INTO quotes (organization_id, survey_id, snapshot, base_cents, uplift_bp, "
            "computed_price_cents, final_price_cents, term_months) "
            "VALUES (:o, :s, '{}', 100, 0, 100, 100, 12) RETURNING id"
        ),
        {"o": org, "s": survey},
    ).scalar_one()


def add_opp(owner, org, name="Deal", **extra):
    cols = {"organization_id": org, "name": name, "stage_id": stage(owner), **extra}
    names = ", ".join(cols)
    values = ", ".join(f":{c}" for c in cols)
    return owner.execute(
        text(f"INSERT INTO opportunities ({names}) VALUES ({values}) RETURNING id"), cols
    ).scalar_one()


def add_reminder(owner, org, agreement, lead_days=90, **extra):
    cols = {
        "organization_id": org,
        "agreement_id": agreement,
        "lead_days": lead_days,
        "due_on": "2026-12-31",
        **extra,
    }
    names = ", ".join(cols)
    values = ", ".join(f":{c}" for c in cols)
    return owner.execute(
        text(f"INSERT INTO renewal_reminders ({names}) VALUES ({values}) RETURNING id"), cols
    ).scalar_one()


def add_lead(owner, **extra):
    cols = {"name": "Pat Prospect", **extra}
    names = ", ".join(cols)
    values = ", ".join(f":{c}" for c in cols)
    return owner.execute(
        text(f"INSERT INTO leads ({names}) VALUES ({values}) RETURNING id"), cols
    ).scalar_one()


def test_seeded_stages(owner):
    rows = owner.execute(
        text(
            "SELECT position, name, probability_bp, kind, active FROM opportunity_stages "
            "ORDER BY position"
        )
    ).all()
    assert rows == [
        (1, "Qualify", 1000, "open", True),
        (2, "Site survey", 2500, "open", True),
        (3, "Proposal", 5000, "open", True),
        (4, "Negotiation", 7500, "open", True),
        (5, "Won", 10000, "won", True),
        (6, "Lost", 0, "lost", True),
    ]


def test_columns(owner):
    def cols(table):
        return {
            r[0]
            for r in owner.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name = :t"),
                {"t": table},
            )
        }

    assert {
        "name", "company", "email", "phone", "source", "status", "owner_id", "notes",
        "converted_organization_id", "converted_at", "created_at", "updated_at",
    } <= cols("leads")  # fmt: skip
    assert {"name", "position", "probability_bp", "kind", "active"} <= cols("opportunity_stages")
    assert {
        "organization_id", "kind", "stage_id", "owner_id", "monthly_cents", "term_months",
        "expected_close_date", "quote_id", "agreement_id", "lost_reason", "closed_at", "notes",
    } <= cols("opportunities")  # fmt: skip
    assert {
        "organization_id", "agreement_id", "lead_days", "due_on", "status", "opportunity_id",
        "email_message_id", "created_at",
    } <= cols("renewal_reminders")  # fmt: skip
    assert {"renewal_reminder_days", "renewal_email"} <= cols("settings")


def test_runtime_role_privileges(owner):
    for table in ALL:
        for p in ("SELECT", "INSERT", "UPDATE", "DELETE"):
            has = owner.execute(
                text("SELECT has_table_privilege('psa_app', :t, :p)"), {"t": table, "p": p}
            ).scalar_one()
            assert has == (p != "DELETE"), (table, p)


def test_rls_forced_on_client_tables_only(owner):
    for table in SCOPED:
        row = owner.execute(
            text("SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = :t"),
            {"t": table},
        ).one()
        assert row == (True, True), table
    for table in ("leads", "opportunity_stages"):
        row = owner.execute(
            text("SELECT relrowsecurity FROM pg_class WHERE relname = :t"), {"t": table}
        ).one()
        assert row == (False,), table


def test_rls_scopes_opportunities_and_reminders(owner, two_orgs):
    a, b = two_orgs
    ag_a, ag_b = add_agreement(owner, a), add_agreement(owner, b)
    add_opp(owner, a, "A")
    add_opp(owner, b, "B")
    add_reminder(owner, a, ag_a)
    add_reminder(owner, b, ag_b)
    with new_session() as db:
        for table in SCOPED:
            assert db.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() == 0
        set_org_scope(db, str(a))
        for table in SCOPED:
            orgs = {r[0] for r in db.execute(text(f"SELECT organization_id FROM {table}"))}
            assert orgs == {a}, table
        set_org_scope(db, "all")
        for table in SCOPED:
            assert db.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() == 2
        db.rollback()


def test_stage_checks(owner):
    def add(**kw):
        cols = {"name": "X", "position": 9, "probability_bp": 0, "kind": "open", **kw}
        owner.execute(
            text(
                "INSERT INTO opportunity_stages (name, position, probability_bp, kind) "
                "VALUES (:name, :position, :probability_bp, :kind)"
            ),
            cols,
        )

    with pytest.raises(IntegrityError, match="ck_opportunity_stages_probability"):
        add(probability_bp=10001)
    with pytest.raises(IntegrityError, match="ck_opportunity_stages_probability"):
        add(probability_bp=-1)
    with pytest.raises(IntegrityError, match="ck_opportunity_stages_kind"):
        add(kind="maybe")
    with pytest.raises(IntegrityError, match="uq_opportunity_stages_name"):
        add(name="Qualify")
    add(name="Edge low", probability_bp=0)
    add(name="Edge high", probability_bp=10000)


def test_only_one_active_won_and_lost_stage(owner):
    with pytest.raises(IntegrityError, match="uq_opportunity_stages_active_terminal"):
        owner.execute(
            text(
                "INSERT INTO opportunity_stages (name, position, probability_bp, kind) "
                "VALUES ('Won again', 9, 10000, 'won')"
            )
        )
    owner.execute(
        text(
            "INSERT INTO opportunity_stages (name, position, probability_bp, kind, active) "
            "VALUES ('Old won', 9, 10000, 'won', false)"
        )
    )


def test_lead_defaults_and_checks(owner):
    lid = add_lead(owner)
    row = owner.execute(text("SELECT status FROM leads WHERE id = :i"), {"i": lid}).one()
    assert row == ("new",)
    for ok in ("contacted", "qualified", "disqualified", "converted"):
        add_lead(owner, status=ok)
    with pytest.raises(IntegrityError, match="ck_leads_status"):
        add_lead(owner, status="weird")


def test_opportunity_checks(owner, two_orgs):
    a, _ = two_orgs
    oid = add_opp(owner, a)
    row = owner.execute(
        text("SELECT kind, monthly_cents, term_months FROM opportunities WHERE id = :i"),
        {"i": oid},
    ).one()
    assert row == ("new", 0, 12)
    with pytest.raises(IntegrityError, match="ck_opportunities_kind"):
        add_opp(owner, a, kind="other")
    with pytest.raises(IntegrityError, match="ck_opportunities_monthly"):
        add_opp(owner, a, monthly_cents=-1)
    for bad in (0, 121):
        with pytest.raises(IntegrityError, match="ck_opportunities_term"):
            add_opp(owner, a, term_months=bad)
    add_opp(owner, a, term_months=1)
    add_opp(owner, a, term_months=120, kind="renewal")
    add_opp(owner, a, kind="upsell")


def test_cross_org_links_rejected(owner, two_orgs):
    a, b = two_orgs
    quote_a, quote_b = add_quote(owner, a), add_quote(owner, b)
    ag_a, ag_b = add_agreement(owner, a), add_agreement(owner, b)
    add_opp(owner, a, quote_id=quote_a, agreement_id=ag_a)
    with pytest.raises(IntegrityError, match="fk_opportunities_quote_org"):
        add_opp(owner, a, quote_id=quote_b)
    with pytest.raises(IntegrityError, match="fk_opportunities_agreement_org"):
        add_opp(owner, a, agreement_id=ag_b)
    opp_b = add_opp(owner, b)
    add_reminder(owner, a, ag_a)
    with pytest.raises(IntegrityError, match="fk_renewal_reminders_agreement_org"):
        add_reminder(owner, a, ag_b)
    with pytest.raises(IntegrityError, match="fk_renewal_reminders_opportunity_org"):
        add_reminder(owner, a, ag_a, lead_days=30, opportunity_id=opp_b)


def test_reminder_rules(owner, two_orgs):
    a, _ = two_orgs
    ag = add_agreement(owner, a)
    rid = add_reminder(owner, a, ag, 90)
    row = owner.execute(
        text("SELECT status FROM renewal_reminders WHERE id = :i"), {"i": rid}
    ).one()
    assert row == ("open",)
    with pytest.raises(IntegrityError, match="uq_renewal_reminders_once"):
        add_reminder(owner, a, ag, 90)
    add_reminder(owner, a, ag, 30)
    with pytest.raises(IntegrityError, match="ck_renewal_reminders_lead_days"):
        add_reminder(owner, a, ag, 0)
    with pytest.raises(IntegrityError, match="ck_renewal_reminders_status"):
        add_reminder(owner, a, ag, 7, status="snoozed")
    for ok in ("done", "dismissed"):
        add_reminder(owner, a, ag, 10 if ok == "done" else 11, status=ok)


def test_settings_renewal_defaults(owner):
    row = owner.execute(text("SELECT renewal_reminder_days, renewal_email FROM settings")).one()
    assert row == ([90, 30], None)
