"""CRM service rules: leads and conversion, opportunities and stage moves, stage config, the
forecast (exact cents) and the quote link / accept hook."""

from contextlib import contextmanager
from datetime import date, timedelta

import pytest
from sqlalchemy import select, text

from app import crm
from app.db import new_session, set_org_scope
from app.deps import Ctx
from app.errors import Conflict, NotFound
from app.models import Agreement, Contact, OpportunityStage, Organization, Quote, User
from app.scope import Scope
from tests.test_crm_schema import add_agreement, add_quote

TODAY = date(2026, 6, 15)


@pytest.fixture
def run(make_user):
    """run(role) -> context manager yielding a Ctx for that role; commits on success."""

    @contextmanager
    def _run(role="admin"):
        who = make_user(role)
        db = new_session()
        try:
            set_org_scope(db, "all")
            yield Ctx(db=db, user=db.get(User, who["id"]), scope=Scope.all())
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    return _run


@pytest.fixture
def org(make_org):
    return make_org("Crm Client")["id"]


def stage(ctx, name=None, kind=None):
    stmt = select(OpportunityStage).where(OpportunityStage.active)
    stmt = stmt.where(OpportunityStage.name == name) if name else stmt
    stmt = stmt.where(OpportunityStage.kind == kind) if kind else stmt
    return ctx.db.execute(stmt.order_by(OpportunityStage.position)).scalars().first()


def opp(ctx, org, **extra):
    return crm.create_opportunity(
        ctx, {"organization_id": org, "name": "Deal", "monthly_cents": 100_00, **extra}
    )


# ---- leads ------------------------------------------------------------------------------------
def test_lead_create_update_and_filter(run):
    with run() as ctx:
        a = crm.create_lead(ctx, {"name": "Pat Prospect", "company": "Widgets Inc"})
        b = crm.create_lead(ctx, {"name": "Sam", "email": "sam@gadgets.example"})
        assert (a.status, a.owner_id) == ("new", None)
        crm.update_lead(ctx, b.id, {"status": "contacted", "owner_id": ctx.user.id})
        assert [x.id for x in crm.list_leads(ctx, status="contacted")] == [b.id]
        assert [x.id for x in crm.list_leads(ctx, owner_id=ctx.user.id)] == [b.id]
        assert [x.id for x in crm.list_leads(ctx, q="WIDGETS")] == [a.id]
        assert [x.id for x in crm.list_leads(ctx, q="gadgets")] == [b.id]
        assert len(crm.list_leads(ctx)) == 2
        with pytest.raises(Conflict):
            crm.update_lead(ctx, a.id, {"owner_id": 99999})
        with pytest.raises(NotFound):
            crm.update_lead(ctx, 99999, {"name": "x"})


def test_convert_needs_a_qualified_lead(run):
    with run() as ctx:
        lead = crm.create_lead(ctx, {"name": "Pat", "status": "contacted"})
        with pytest.raises(Conflict, match="qualified"):
            crm.convert_lead(ctx, lead.id, {})


def test_convert_creates_prospect_contact_and_opportunity_and_only_once(run):
    with run() as ctx:
        lead = crm.create_lead(
            ctx,
            {
                "name": "Pat Prospect",
                "company": "Widgets Inc",
                "email": "pat@widgets.example",
                "phone": "555-0100",
                "status": "qualified",
            },
        )
        o = crm.convert_lead(ctx, lead.id, {"monthly_cents": 250_000, "term_months": 24})
        assert o.kind == "new" and o.owner_id == ctx.user.id
        assert o.stage_id == stage(ctx, "Qualify").id
        assert (o.monthly_cents, o.term_months) == (250_000, 24)
        org = ctx.db.get(Organization, o.organization_id)
        assert (org.name, org.status) == ("Widgets Inc", "prospect")
        [contact] = ctx.db.execute(
            select(Contact).where(Contact.organization_id == org.id)
        ).scalars()
        assert (contact.name, contact.email, contact.phone) == (
            "Pat Prospect",
            "pat@widgets.example",
            "555-0100",
        )
        assert contact.is_primary
        assert lead.status == "converted" and lead.converted_organization_id == org.id
        assert lead.converted_at is not None
        with pytest.raises(Conflict, match="already"):
            crm.convert_lead(ctx, lead.id, {})
        with pytest.raises(Conflict, match="read-only"):
            crm.update_lead(ctx, lead.id, {"notes": "late"})


def test_convert_uses_the_contact_name_when_there_is_no_company_and_the_lead_owner(run, make_user):
    other = make_user("tech")
    with run() as ctx:
        lead = crm.create_lead(
            ctx, {"name": "Solo Sam", "status": "qualified", "owner_id": other["id"]}
        )
        o = crm.convert_lead(ctx, lead.id, {})
        assert ctx.db.get(Organization, o.organization_id).name == "Solo Sam"
        assert o.owner_id == other["id"]


def test_convert_with_a_taken_organization_name_is_a_conflict(run, make_org):
    make_org("Widgets Inc")
    with run() as ctx:
        lead = crm.create_lead(
            ctx, {"name": "Pat", "company": "Widgets Inc", "status": "qualified"}
        )
        with pytest.raises(Conflict):
            crm.convert_lead(ctx, lead.id, {})


# ---- opportunities ----------------------------------------------------------------------------
def test_create_defaults_to_the_first_open_stage_and_rejects_closed_stages(run, org):
    with run() as ctx:
        o = opp(ctx, org)
        assert o.stage_id == stage(ctx, "Qualify").id and o.owner_id == ctx.user.id
        assert o.term_months == 12 and o.closed_at is None
        with pytest.raises(Conflict):
            opp(ctx, org, stage_id=stage(ctx, kind="won").id)
        with pytest.raises(NotFound):
            opp(ctx, 99999)
        p = opp(ctx, org, stage_id=stage(ctx, "Proposal").id)
        assert p.stage_id == stage(ctx, "Proposal").id


def test_update_changes_the_editable_fields_only(run, org):
    with run() as ctx:
        o = opp(ctx, org)
        won = stage(ctx, kind="won").id
        crm.update_opportunity(
            ctx, o.id, {"name": "Bigger", "monthly_cents": 5, "stage_id": won, "kind": "upsell"}
        )
        assert (o.name, o.monthly_cents, o.kind) == ("Bigger", 5, "new")
        assert o.stage_id == stage(ctx, "Qualify").id


def test_lost_needs_a_reason_won_sets_closed_at_and_reopening_clears_it(run, org):
    with run() as ctx:
        o = opp(ctx, org)
        lost, won = stage(ctx, kind="lost").id, stage(ctx, kind="won").id
        with pytest.raises(Conflict, match="lost reason"):
            crm.move_stage(ctx, o.id, lost)
        with pytest.raises(Conflict, match="lost reason"):
            crm.move_stage(ctx, o.id, lost, "   ")
        assert o.closed_at is None
        crm.move_stage(ctx, o.id, lost, "Chose a competitor")
        assert o.closed_at is not None and o.lost_reason == "Chose a competitor"
        crm.move_stage(ctx, o.id, won)
        assert o.closed_at is not None and o.lost_reason is None
        crm.move_stage(ctx, o.id, stage(ctx, "Proposal").id)
        assert o.closed_at is None and o.lost_reason is None


def test_cannot_move_into_an_inactive_stage(run, org):
    with run() as ctx:
        o = opp(ctx, org)
        s = stage(ctx, "Site survey")
        crm.update_stage(ctx, s.id, {"active": False})
        with pytest.raises(Conflict):
            crm.move_stage(ctx, o.id, s.id)
        with pytest.raises(NotFound):
            crm.move_stage(ctx, o.id, 99999)


def test_list_filters(run, org, make_org):
    other = make_org("Other Client")["id"]
    with run() as ctx:
        a = opp(ctx, org, expected_close_date=TODAY + timedelta(days=5))
        b = opp(ctx, other, kind="upsell")
        c = opp(ctx, org)
        crm.move_stage(ctx, c.id, stage(ctx, kind="won").id)
        assert {x.id for x in crm.list_opportunities(ctx)} == {a.id, b.id, c.id}
        assert {x.id for x in crm.list_opportunities(ctx, organization_id=org)} == {a.id, c.id}
        assert [x.id for x in crm.list_opportunities(ctx, kind="upsell")] == [b.id]
        assert {x.id for x in crm.list_opportunities(ctx, open_only=True)} == {a.id, b.id}
        assert [x.id for x in crm.list_opportunities(ctx, stage_id=c.stage_id)] == [c.id]
        assert [x.id for x in crm.list_opportunities(ctx, owner_id=ctx.user.id)][0] == a.id


# ---- stage config -----------------------------------------------------------------------------
def test_the_only_won_or_lost_stage_cannot_be_deactivated(run):
    with run() as ctx:
        for kind in ("won", "lost"):
            with pytest.raises(Conflict, match=kind):
                crm.update_stage(ctx, stage(ctx, kind=kind).id, {"active": False})


def test_a_second_active_won_stage_is_refused_but_activating_one_swaps(run):
    with run() as ctx:
        with pytest.raises(Conflict):
            crm.create_stage(
                ctx, {"name": "Signed", "position": 7, "probability_bp": 10000, "kind": "won"}
            )
    with run() as ctx:
        old = stage(ctx, kind="won")
        new = crm.create_stage(
            ctx,
            {
                "name": "Signed",
                "position": 7,
                "probability_bp": 10000,
                "kind": "won",
                "active": False,
            },
        )
        assert new.active is False
        crm.update_stage(ctx, new.id, {"active": True})
        assert stage(ctx, kind="won").id == new.id and old.active is False


def test_stage_names_are_unique_and_the_last_open_stage_stays(run):
    with run() as ctx:
        with pytest.raises(Conflict):
            crm.create_stage(
                ctx, {"name": "Qualify", "position": 9, "probability_bp": 500, "kind": "open"}
            )
    with run() as ctx:
        opens = [s for s in crm.list_stages(ctx) if s.kind == "open"]
        for s in opens[:-1]:
            crm.update_stage(ctx, s.id, {"active": False})
        with pytest.raises(Conflict, match="open"):
            crm.update_stage(ctx, opens[-1].id, {"active": False})
        assert crm.first_open_stage(ctx).id == opens[-1].id


def test_stage_edit_changes_probability_and_order(run):
    with run() as ctx:
        s = stage(ctx, "Proposal")
        crm.update_stage(ctx, s.id, {"probability_bp": 6000, "position": 0})
        assert crm.list_stages(ctx)[0].id == s.id and s.probability_bp == 6000
        assert [x.name for x in crm.list_stages(ctx, include_inactive=False)][0] == "Proposal"


# ---- forecast ---------------------------------------------------------------------------------
def test_forecast_with_nothing_is_all_zero_buckets(run):
    with run() as ctx:
        f = crm.forecast(ctx, TODAY)
        keys = [b["key"] for b in f["buckets"]]
        assert keys[0] == "overdue" and keys[-1] == "no_date"
        assert keys[1:13] == [
            "2026-06", "2026-07", "2026-08", "2026-09", "2026-10", "2026-11",
            "2026-12", "2027-01", "2027-02", "2027-03", "2027-04", "2027-05",
        ]  # fmt: skip
        for b in [*f["buckets"], f["total"], f["won_this_month"], f["won_this_quarter"]]:
            assert (b["count"], b["monthly_cents"], b["weighted_monthly_cents"]) == (0, 0, 0)
            assert b["contract_value_cents"] == 0


def test_weighted_rounding_is_half_up_per_opportunity(run, org):
    with run() as ctx:
        o = opp(ctx, org, monthly_cents=333, expected_close_date=TODAY)
        crm.update_stage(ctx, stage(ctx, "Qualify").id, {"probability_bp": 5000})
        f = crm.forecast(ctx, TODAY)
        june = next(b for b in f["buckets"] if b["key"] == "2026-06")
        assert june["weighted_monthly_cents"] == 167  # 166.5 -> 167
        opp(ctx, org, monthly_cents=333, expected_close_date=TODAY)
        june = next(b for b in crm.forecast(ctx, TODAY)["buckets"] if b["key"] == "2026-06")
        assert june["weighted_monthly_cents"] == 334  # rounded per opportunity, not on the sum
        assert o.id


def test_forecast_buckets_dates_and_sums_contract_value(run, org):
    with run() as ctx:
        prop = stage(ctx, "Proposal").id  # 50%
        opp(ctx, org, monthly_cents=1000, term_months=12, stage_id=prop, expected_close_date=TODAY)
        opp(
            ctx, org, monthly_cents=2000, term_months=24, stage_id=prop,
            expected_close_date=date(2026, 6, 30),
        )  # fmt: skip
        opp(
            ctx,
            org,
            monthly_cents=500,
            stage_id=prop,
            expected_close_date=TODAY - timedelta(days=1),
        )
        opp(ctx, org, monthly_cents=700, stage_id=prop)
        opp(ctx, org, monthly_cents=900, stage_id=prop, expected_close_date=date(2028, 1, 1))
        f = crm.forecast(ctx, TODAY)
        by = {b["key"]: b for b in f["buckets"]}
        assert by["2026-06"] == {
            "key": "2026-06", "label": "Jun 2026", "count": 2, "monthly_cents": 3000,
            "weighted_monthly_cents": 1500, "contract_value_cents": 1000 * 12 + 2000 * 24,
        }  # fmt: skip
        assert (by["overdue"]["count"], by["overdue"]["monthly_cents"]) == (1, 500)
        assert (by["no_date"]["count"], by["no_date"]["weighted_monthly_cents"]) == (1, 350)
        assert by["later"]["count"] == 1
        assert f["total"]["count"] == 5 and f["total"]["monthly_cents"] == 5100


def test_forecast_ignores_closed_deals_and_reports_wins_this_month(run, org):
    with run() as ctx:
        a = opp(ctx, org, monthly_cents=4000, term_months=12)
        b = opp(ctx, org, monthly_cents=999)
        crm.move_stage(ctx, a.id, stage(ctx, kind="won").id)
        crm.move_stage(ctx, b.id, stage(ctx, kind="lost").id, "No budget")
        now_day = date.today()
        f = crm.forecast(ctx, now_day)
        assert f["total"]["count"] == 0
        assert (f["won_this_month"]["count"], f["won_this_month"]["monthly_cents"]) == (1, 4000)
        assert f["won_this_month"]["contract_value_cents"] == 48_000
        assert f["won_this_quarter"]["count"] == 1
        later = crm.forecast(ctx, now_day + timedelta(days=200))
        assert later["won_this_month"]["count"] == 0


# ---- quote link and accept hook ---------------------------------------------------------------
def test_link_quote_must_be_same_client_and_the_opportunity_open(run, org, make_org, owner):
    other = make_org("Elsewhere")["id"]
    mine, theirs = add_quote(owner, org), add_quote(owner, other)
    with run() as ctx:
        o = opp(ctx, org)
        with pytest.raises(Conflict, match="different client"):
            crm.link_quote(ctx, o.id, theirs)
        with pytest.raises(Conflict, match="different client"):
            crm.link_quote(ctx, o.id, 99999)
        assert crm.link_quote(ctx, o.id, mine).quote_id == mine
        crm.move_stage(ctx, o.id, stage(ctx, kind="lost").id, "Gone")
        with pytest.raises(Conflict, match="closed"):
            crm.link_quote(ctx, o.id, mine)


def test_only_an_open_quote_can_be_linked(run, org, owner):
    q = add_quote(owner, org)
    owner.execute(text("UPDATE quotes SET status = 'cancelled' WHERE id = :q"), {"q": q})
    with run() as ctx:
        o = opp(ctx, org)
        with pytest.raises(Conflict, match="cancelled"):
            crm.link_quote(ctx, o.id, q)


def test_accepting_wins_linked_open_opportunities_and_keeps_a_renewal_agreement(run, org, owner):
    quote_id = add_quote(owner, org)
    renewing = add_agreement(owner, org, "Old MSP")
    resulting = add_agreement(owner, org, "New MSP")
    with run() as ctx:
        new = opp(ctx, org)
        renewal = opp(ctx, org, kind="renewal", agreement_id=renewing)
        closed = opp(ctx, org)
        unlinked = opp(ctx, org)
        for o in (new, renewal, closed):
            crm.link_quote(ctx, o.id, quote_id)
        crm.move_stage(ctx, closed.id, stage(ctx, kind="lost").id, "Went away")
        ctx.db.get(Quote, quote_id)
        won = crm.on_quote_accepted(
            ctx, ctx.db.get(Quote, quote_id), ctx.db.get(Agreement, resulting)
        )
        assert {o.id for o in won} == {new.id, renewal.id}
        won_stage = stage(ctx, kind="won").id
        assert (new.stage_id, new.agreement_id) == (won_stage, resulting)
        assert (renewal.stage_id, renewal.agreement_id) == (won_stage, renewing)
        assert new.closed_at is not None
        assert closed.stage_id == stage(ctx, kind="lost").id
        assert unlinked.stage_id == stage(ctx, "Qualify").id
