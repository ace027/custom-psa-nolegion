"""Renewal reminders: one per configured lead time per agreement, the renewal opportunity, the
optional email, closing out and dismissal. Every date is explicit."""

from contextlib import contextmanager
from datetime import date, timedelta

import pytest
from sqlalchemy import select, text

from app import crm, renewals
from app.db import new_session, set_org_scope
from app.deps import Ctx
from app.errors import Conflict, NotFound
from app.models import EmailMessage, Opportunity, OpportunityStage, RenewalReminder, User
from app.scope import Scope

END = date(2026, 12, 31)


@pytest.fixture
def run(make_user):
    @contextmanager
    def _run():
        who = make_user("admin")
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
    return make_org("Renewing Client")["id"]


def agreement(owner, org, end=END, name="Managed services", type_="flat", price=150_000, qty=1):
    return owner.execute(
        text(
            "INSERT INTO agreements (organization_id, name, type, unit_price_cents, quantity, "
            "start_date, end_date) VALUES (:o, :n, :t, :p, :q, '2026-01-01', :e) RETURNING id"
        ),
        {"o": org, "n": name, "t": type_, "p": price, "q": qty, "e": end},
    ).scalar_one()


def reminders(ctx):
    return list(
        ctx.db.execute(
            select(RenewalReminder).order_by(
                RenewalReminder.agreement_id, RenewalReminder.lead_days
            )
        ).scalars()
    )


def renewal_opps(ctx):
    return list(ctx.db.execute(select(Opportunity).where(Opportunity.kind == "renewal")).scalars())


def stage_id(ctx, kind):
    return (
        ctx.db.execute(
            select(OpportunityStage.id).where(
                OpportunityStage.kind == kind, OpportunityStage.active
            )
        )
        .scalars()
        .first()
    )


def test_agreements_without_a_usable_end_date_get_no_reminders(run, owner, org):
    agreement(owner, org, end=None, name="Open ended")
    agreement(owner, org, end=END - timedelta(days=1), name="Ended already")
    with run() as ctx:
        counts = renewals.scan(ctx, END)
        assert counts == {"reminders": 0, "opportunities": 0, "emails": 0, "done": 0, "errors": 0}
        assert reminders(ctx) == [] and renewal_opps(ctx) == []


def test_a_failing_agreement_is_skipped_and_counted_without_losing_the_others(run, owner, org):
    agreement(owner, org, name="Needs an opportunity")
    with run() as ctx:
        for st in ctx.db.execute(
            select(OpportunityStage).where(OpportunityStage.kind == "open")
        ).scalars():
            st.active = False
        ctx.db.flush()
        counts = renewals.scan(ctx, END - timedelta(days=89))
        assert counts["errors"] == 1 and counts["reminders"] == 0
        assert reminders(ctx) == [] and renewal_opps(ctx) == []


def test_one_bad_agreement_does_not_stop_the_next_one(run, owner, org, monkeypatch):
    bad = agreement(owner, org, name="Bad")
    good = agreement(owner, org, name="Good")
    real = crm.create_opportunity

    def flaky(ctx, data):
        if data["agreement_id"] == bad:
            raise Conflict("boom")
        return real(ctx, data)

    monkeypatch.setattr(crm, "create_opportunity", flaky)
    with run() as ctx:
        counts = renewals.scan(ctx, END - timedelta(days=89))
        assert counts["errors"] == 1 and counts["reminders"] == 1
        assert [r.agreement_id for r in reminders(ctx)] == [good]


def test_nothing_is_due_100_days_out(run, owner, org):
    agreement(owner, org)
    with run() as ctx:
        assert renewals.scan(ctx, END - timedelta(days=100))["reminders"] == 0
        assert reminders(ctx) == []


def test_89_days_out_creates_the_90_day_reminder_and_the_renewal_opportunity(run, owner, org):
    ag = agreement(owner, org, type_="per_user", price=2500, qty=12)
    with run() as ctx:
        counts = renewals.scan(ctx, END - timedelta(days=89))
        assert counts["reminders"] == 1 and counts["opportunities"] == 1
        [r] = reminders(ctx)
        assert (r.lead_days, r.due_on, r.status, r.agreement_id) == (90, END, "open", ag)
        [o] = renewal_opps(ctx)
        assert (o.agreement_id, o.monthly_cents, o.term_months) == (ag, 30_000, 12)
        assert o.expected_close_date == END and o.organization_id == org
        assert o.stage_id == crm.first_open_stage(ctx).id and o.name == "Renewal: Managed services"
        assert r.opportunity_id == o.id and r.email_message_id is None


def test_29_days_out_adds_only_the_30_day_reminder_and_no_second_opportunity(run, owner, org):
    agreement(owner, org)
    with run() as ctx:
        renewals.scan(ctx, END - timedelta(days=89))
    with run() as ctx:
        counts = renewals.scan(ctx, END - timedelta(days=29))
        assert counts["reminders"] == 1 and counts["opportunities"] == 0
        assert [r.lead_days for r in reminders(ctx)] == [30, 90]
        [o] = renewal_opps(ctx)
        assert {r.opportunity_id for r in reminders(ctx)} == {o.id}


def test_a_first_run_inside_both_windows_creates_both_reminders_and_one_opportunity(
    run, owner, org
):
    agreement(owner, org)
    with run() as ctx:
        counts = renewals.scan(ctx, END - timedelta(days=29))
        assert (counts["reminders"], counts["opportunities"]) == (2, 1)


def test_scanning_again_creates_nothing(run, owner, org):
    agreement(owner, org)
    with run() as ctx:
        renewals.scan(ctx, END - timedelta(days=10))
    with run() as ctx:
        counts = renewals.scan(ctx, END - timedelta(days=10))
        assert counts == {"reminders": 0, "opportunities": 0, "emails": 0, "done": 0, "errors": 0}
        assert len(reminders(ctx)) == 2 and len(renewal_opps(ctx)) == 1


def test_the_end_date_itself_still_counts_the_day_after_does_not(run, owner, org):
    agreement(owner, org)
    with run() as ctx:
        assert renewals.scan(ctx, END + timedelta(days=1))["reminders"] == 0
        assert renewals.scan(ctx, END)["reminders"] == 2


def test_an_existing_open_renewal_opportunity_is_reused(run, owner, org):
    ag = agreement(owner, org)
    with run() as ctx:
        mine = crm.create_opportunity(
            ctx,
            {
                "organization_id": org,
                "name": "Hand made renewal",
                "kind": "renewal",
                "agreement_id": ag,
            },
        )
        counts = renewals.scan(ctx, END - timedelta(days=89))
        assert counts["opportunities"] == 0
        assert reminders(ctx)[0].opportunity_id == mine.id


def test_configured_lead_times_are_used(run, owner, org):
    agreement(owner, org)
    owner.execute(text("UPDATE settings SET renewal_reminder_days = '{60,7}'"))
    with run() as ctx:
        assert renewals.scan(ctx, END - timedelta(days=89))["reminders"] == 0
        assert renewals.scan(ctx, END - timedelta(days=59))["reminders"] == 1
        assert [r.lead_days for r in reminders(ctx)] == [60]


def test_a_dismissed_reminder_is_not_recreated(run, owner, org):
    agreement(owner, org)
    with run() as ctx:
        renewals.scan(ctx, END - timedelta(days=89))
        [r] = reminders(ctx)
        out = renewals.dismiss(ctx, r.id)
        assert out["status"] == "dismissed" and out["agreement_name"] == "Managed services"
        with pytest.raises(Conflict, match="dismissed"):
            renewals.dismiss(ctx, r.id)
    with run() as ctx:
        assert renewals.scan(ctx, END - timedelta(days=89))["reminders"] == 0
        [r] = reminders(ctx)
        assert r.status == "dismissed"
        with pytest.raises(NotFound):
            renewals.dismiss(ctx, 99999)


def test_email_is_set_but_no_mailbox_so_the_reminder_exists_without_an_email(run, owner, org):
    agreement(owner, org)
    owner.execute(text("UPDATE settings SET renewal_email = 'boss@msp.example'"))
    with run() as ctx:
        counts = renewals.scan(ctx, END - timedelta(days=89))
        assert (counts["reminders"], counts["emails"]) == (1, 0)
        assert reminders(ctx)[0].email_message_id is None
        assert ctx.db.execute(select(EmailMessage)).first() is None


def test_email_is_queued_once_per_reminder_when_a_mailbox_exists(
    run, owner, org, mail_ready, monkeypatch
):
    agreement(owner, org)
    owner.execute(text("UPDATE settings SET renewal_email = 'boss@msp.example'"))
    with run() as ctx:
        counts = renewals.scan(ctx, END - timedelta(days=89))
        assert (counts["reminders"], counts["emails"]) == (1, 1)
        [r] = reminders(ctx)
        mail = ctx.db.get(EmailMessage, r.email_message_id)
        assert mail.direction == "out" and mail.send_status == "pending" and mail.auto_generated
        assert mail.to_emails == ["boss@msp.example"] and mail.organization_id == org
        assert mail.subject == "PSA: agreement Managed services for Renewing Client ends 2026-12-31"
        assert "/crm/renewals" in mail.body_text and "2026-12-31" in mail.body_text
    with run() as ctx:
        assert renewals.scan(ctx, END - timedelta(days=89))["emails"] == 0
        assert ctx.db.query(EmailMessage).count() == 1


def test_a_won_or_lost_renewal_opportunity_marks_its_open_reminders_done(run, owner, org):
    agreement(owner, org, name="One")
    agreement(owner, org, name="Two")
    with run() as ctx:
        renewals.scan(ctx, END - timedelta(days=29))
        one, two = sorted(renewal_opps(ctx), key=lambda o: o.id)
        assert all(r.status == "open" for r in reminders(ctx))
        crm.move_stage(ctx, one.id, stage_id(ctx, "won"))
        crm.move_stage(ctx, two.id, stage_id(ctx, "lost"), "Moving to a competitor")
    with run() as ctx:
        counts = renewals.scan(ctx, END - timedelta(days=28))
        assert counts["done"] == 4
        assert {r.status for r in reminders(ctx)} == {"done"}
        assert renewals.scan(ctx, END - timedelta(days=27))["done"] == 0


def test_list_reminders_filters_by_status_and_names_the_client(run, owner, org, make_org):
    agreement(owner, org)
    agreement(
        owner, make_org("Second Client")["id"], name="Other plan", end=END + timedelta(days=5)
    )
    with run() as ctx:
        renewals.scan(ctx, END - timedelta(days=29))
        rows = renewals.list_reminders(ctx)
        assert [(r["agreement_name"], r["lead_days"]) for r in rows] == [
            ("Managed services", 90),
            ("Managed services", 30),
            ("Other plan", 90),
        ]
        assert [r["organization_name"] for r in rows][-1] == "Second Client"
        renewals.dismiss(ctx, rows[0]["id"])
        assert len(renewals.list_reminders(ctx, "open")) == len(rows) - 1
        assert len(renewals.list_reminders(ctx, "dismissed")) == 1
        assert renewals.list_reminders(ctx, "done") == []


def test_a_won_renewal_is_not_reopened_by_the_30_day_reminder(run, owner, org):
    agreement(owner, org)
    with run() as ctx:
        renewals.scan(ctx, END - timedelta(days=89))
        [o] = renewal_opps(ctx)
        crm.move_stage(ctx, o.id, stage_id(ctx, "won"))
    with run() as ctx:
        counts = renewals.scan(ctx, END - timedelta(days=29))
        assert counts["reminders"] == 1 and counts["opportunities"] == 0 and counts["emails"] == 0
        assert len(renewal_opps(ctx)) == 1
        assert [(r.lead_days, r.status) for r in reminders(ctx)] == [(30, "done"), (90, "done")]


def test_a_lost_renewal_is_not_reopened_either(run, owner, org):
    agreement(owner, org)
    with run() as ctx:
        renewals.scan(ctx, END - timedelta(days=89))
        [o] = renewal_opps(ctx)
        crm.move_stage(ctx, o.id, stage_id(ctx, "lost"), "Going elsewhere")
    with run() as ctx:
        assert renewals.scan(ctx, END - timedelta(days=29))["opportunities"] == 0
        assert len(renewal_opps(ctx)) == 1


def test_a_repriced_agreement_does_not_spawn_a_renewal_for_the_old_one(run, owner, org):
    eff = END - timedelta(days=40)  # first of the new price; the old agreement ends the day before
    old = agreement(owner, org, end=eff - timedelta(days=1), name="Old price")
    owner.execute(
        text(
            "INSERT INTO agreements (organization_id, name, type, unit_price_cents, quantity, "
            "start_date, end_date, notes) VALUES (:o, 'New price', 'flat', 120000, 1, :s, :e, "
            "'Created from quote Q-1')"
        ),
        {"o": org, "s": eff, "e": END},
    )
    with run() as ctx:
        renewals.scan(ctx, eff - timedelta(days=10))
        assert [r for r in reminders(ctx) if r.agreement_id == old] == []
        assert [o for o in renewal_opps(ctx) if o.agreement_id == old] == []


def test_moving_the_end_date_after_a_scan_moves_the_reminders_and_the_email(
    run, owner, org, mail_ready
):
    ag = agreement(owner, org)
    owner.execute(text("UPDATE settings SET renewal_email = 'boss@msp.example'"))
    with run() as ctx:
        renewals.scan(ctx, END - timedelta(days=89))
        assert [r.due_on for r in reminders(ctx)] == [END]
    new_end = END + timedelta(days=30)
    owner.execute(
        text("UPDATE agreements SET end_date = :e WHERE id = :i"), {"e": new_end, "i": ag}
    )
    with run() as ctx:
        renewals.scan(ctx, END - timedelta(days=80))
        assert all(r.due_on == new_end for r in reminders(ctx) if r.status == "open")
    with run() as ctx:
        renewals.scan(ctx, new_end - timedelta(days=89))
        open_90 = [r for r in reminders(ctx) if r.status == "open" and r.lead_days == 90]
        assert len(open_90) == 1 and open_90[0].due_on == new_end
        subjects = [m.subject for m in ctx.db.execute(select(EmailMessage)).scalars()]
        assert any(new_end.isoformat() in s for s in subjects)
        [o] = renewal_opps(ctx)
        assert o.expected_close_date == new_end
