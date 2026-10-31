"""Project service rules: billing fields, approval, transitions, phases, tasks, dependency
cycles, attached tickets and budget vs actual (exact cents)."""

from contextlib import contextmanager

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from app import projects as svc
from app.db import new_session, set_org_scope
from app.deps import Ctx
from app.errors import Conflict, NotFound
from app.models import User
from app.scope import Scope


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
    return make_org("Proj Client")["id"]


def mk(ctx, org, **extra):
    return svc.create_project(ctx, {"organization_id": org, "name": "Rollout", **extra})


def mk_tm(ctx, org, budget=100_000):
    return mk(ctx, org, billing_mode="tm", budget_cents=budget)


def task(ctx, project, title="T", **extra):
    return svc.add_task(ctx, project.id, {"title": title, **extra})


# ---- billing fields and approval ----
def test_tech_creates_draft_without_billing_fields(run, org):
    with run("tech") as ctx:
        p = mk(ctx, org, description="d")
        assert p.status == "draft" and p.billing_mode is None and p.taxable is False


@pytest.mark.parametrize(
    "extra",
    [
        {"billing_mode": "tm"},
        {"fixed_fee_cents": 5000},
        {"budget_cents": 5000},
        {"taxable": True},
    ],
)
def test_tech_cannot_set_billing_fields(run, org, extra):
    with run("tech") as ctx, pytest.raises(HTTPException) as exc:
        mk(ctx, org, **extra)
    assert exc.value.status_code == 403 and exc.value.detail == "Not permitted"


def test_tech_cannot_patch_billing_fields_or_approve(run, org):
    with run("admin") as ctx:
        pid = mk_tm(ctx, org).id
    with run("tech") as ctx:
        with pytest.raises(HTTPException) as exc:
            svc.update_project(ctx, pid, {"budget_cents": 5})
        assert exc.value.status_code == 403
        assert svc.update_project(ctx, pid, {"name": "Renamed"}).name == "Renamed"
        with pytest.raises(HTTPException):
            svc.approve(ctx, pid)


def test_read_only_user_cannot_bill(run, org):
    with run("read_only") as ctx:
        assert svc.can_bill(ctx) is False


def test_billing_role_can_approve(run, org):
    with run("admin") as ctx:
        pid = mk_tm(ctx, org).id
    with run("billing") as ctx:
        assert svc.approve(ctx, pid).status == "active"


def test_approve_requires_mode_and_amount(run, org):
    with run() as ctx:
        no_mode = mk(ctx, org).id
        fixed_no_fee = mk(ctx, org, billing_mode="fixed_fee", budget_cents=5000).id
        tm_no_budget = mk(ctx, org, billing_mode="tm", fixed_fee_cents=5000).id
    for pid in (no_mode, fixed_no_fee, tm_no_budget):
        with run() as ctx, pytest.raises(Conflict):
            svc.approve(ctx, pid)


def test_approve_records_who_and_when_and_only_once(run, org):
    with run() as ctx:
        p = mk(ctx, org, billing_mode="fixed_fee", fixed_fee_cents=250_000)
        done = svc.approve(ctx, p.id)
        assert done.status == "active" and done.approved_at and done.approved_by_id == ctx.user.id
        with pytest.raises(Conflict):
            svc.approve(ctx, p.id)


def test_billing_fields_lock_after_approval_but_tm_budget_moves(run, org, owner):
    with run() as ctx:
        fixed = mk(ctx, org, billing_mode="fixed_fee", fixed_fee_cents=1000)
        tm = mk_tm(ctx, org, 5000)
        svc.approve(ctx, fixed.id)
        svc.approve(ctx, tm.id)
        for key, val in (("billing_mode", "tm"), ("fixed_fee_cents", 2000), ("taxable", True)):
            with pytest.raises(Conflict):
                svc.update_project(ctx, fixed.id, {key: val})
        with pytest.raises(Conflict):
            svc.update_project(ctx, fixed.id, {"budget_cents": 99})
        with pytest.raises(Conflict):
            svc.update_project(ctx, tm.id, {"billing_mode": "fixed_fee"})
        with pytest.raises(Conflict):
            svc.update_project(ctx, tm.id, {"budget_cents": None})
        # sending the same value is not a change
        svc.update_project(ctx, fixed.id, {"billing_mode": "fixed_fee", "fixed_fee_cents": 1000})
        assert svc.update_project(ctx, tm.id, {"budget_cents": 9000}).budget_cents == 9000
        tm_id = tm.id
    audit = owner.execute(
        text(
            "SELECT detail FROM audit_log WHERE action = 'project.budget_change' AND entity_id = :i"
        ),
        {"i": tm_id},
    ).all()
    assert len(audit) == 1 and audit[0].detail["budget_cents"] == [5000, 9000]


def test_draft_billing_fields_can_change_and_clear(run, org):
    with run() as ctx:
        p = mk_tm(ctx, org, 5000)
        p = svc.update_project(ctx, p.id, {"billing_mode": "fixed_fee", "fixed_fee_cents": 700})
        assert (p.billing_mode, p.fixed_fee_cents) == ("fixed_fee", 700)
        p = svc.update_project(ctx, p.id, {"billing_mode": None})
        assert p.billing_mode is None


def test_project_validation(run, org):
    with run() as ctx:
        with pytest.raises(NotFound):
            svc.create_project(ctx, {"organization_id": 999_999, "name": "x"})
        with pytest.raises(Conflict):
            mk(ctx, org, owner_id=999_999)
        from datetime import date

        with pytest.raises(Conflict):
            mk(ctx, org, start_date=date(2026, 5, 2), due_date=date(2026, 5, 1))
        with pytest.raises(NotFound):
            svc.get_project(ctx, 999_999)


# ---- status transitions ----
@pytest.mark.parametrize(
    "path,bad",
    [
        (["cancelled"], "active"),
        (["cancelled"], "draft"),
        (["cancelled"], "cancelled"),
        (["active", "completed"], "active"),
        (["active", "completed"], "cancelled"),
        (["active", "on_hold"], "completed"),
        (["active"], "draft"),
    ],
)
def test_illegal_status_transitions(run, org, path, bad):
    with run() as ctx:
        p = mk_tm(ctx, org)
        if path[0] == "active":
            svc.approve(ctx, p.id)
            path = path[1:]
        for step in path:
            svc.set_status(ctx, p.id, step)
        with pytest.raises(Conflict):
            svc.set_status(ctx, p.id, bad)


def test_legal_status_transitions(run, org):
    with run() as ctx:
        p = mk_tm(ctx, org)
        with pytest.raises(Conflict):  # activation goes through approve
            svc.set_status(ctx, p.id, "active")
        svc.approve(ctx, p.id)
        for step in ("on_hold", "active", "completed"):
            assert svc.set_status(ctx, p.id, step).status == step
        draft = mk(ctx, org)
        assert svc.set_status(ctx, draft.id, "cancelled").status == "cancelled"


def test_list_filters(run, org, make_org):
    other = make_org("Other")["id"]
    with run() as ctx:
        a, b = mk(ctx, org), mk(ctx, other)
        svc.set_status(ctx, b.id, "cancelled")
        assert {p.id for p in svc.list_projects(ctx)} == {a.id, b.id}
        assert [p.id for p in svc.list_projects(ctx, organization_id=org)] == [a.id]
        assert [p.id for p in svc.list_projects(ctx, status="cancelled")] == [b.id]


# ---- phases ----
def test_phase_lifecycle(run, org):
    with run() as ctx:
        p = mk(ctx, org)
        one, two = (
            svc.add_phase(ctx, p.id, {"name": "Plan"}),
            svc.add_phase(ctx, p.id, {"name": "Build"}),
        )
        assert (one.position, two.position) == (0, 1)
        assert svc.update_phase(ctx, p.id, one.id, {"name": "Design"}).name == "Design"
        done = svc.update_phase(ctx, p.id, one.id, {"completed": True})
        assert done.completed_at is not None
        assert svc.update_phase(ctx, p.id, one.id, {"completed": False}).completed_at is None
        svc.delete_phase(ctx, p.id, two.id)
        with pytest.raises(NotFound):
            svc.update_phase(ctx, p.id, two.id, {"name": "x"})


def test_phase_with_tasks_cannot_be_deleted(run, org):
    with run() as ctx:
        p = mk(ctx, org)
        ph = svc.add_phase(ctx, p.id, {"name": "Plan"})
        t = task(ctx, p, phase_id=ph.id)
        with pytest.raises(Conflict):
            svc.delete_phase(ctx, p.id, ph.id)
        svc.update_task(ctx, p.id, t.id, {"phase_id": None})
        svc.delete_phase(ctx, p.id, ph.id)


def test_phase_of_another_project_is_not_found(run, org):
    with run() as ctx:
        a, b = mk(ctx, org), mk(ctx, org)
        ph = svc.add_phase(ctx, a.id, {"name": "Plan"})
        with pytest.raises(NotFound):
            task(ctx, b, phase_id=ph.id)
        with pytest.raises(NotFound):
            svc.delete_phase(ctx, b.id, ph.id)


def test_closed_project_takes_no_new_structure(run, org):
    with run() as ctx:
        p = mk(ctx, org)
        svc.set_status(ctx, p.id, "cancelled")
        with pytest.raises(Conflict):
            svc.add_phase(ctx, p.id, {"name": "x"})
        with pytest.raises(Conflict):
            task(ctx, p)


# ---- tasks ----
def test_task_creates_its_project_ticket(run, org, make_user):
    tech = make_user("tech", "t@example.com")
    with run() as ctx:
        p = mk(ctx, org)
        t = task(
            ctx, p, "Cable runs", description="d", assignee_id=tech["id"], estimate_minutes=120
        )
        assert t.ticket.source == "project" and t.ticket.project_id == p.id
        assert t.ticket.subject == "Cable runs" and t.ticket.assignee_id == tech["id"]
        assert t.ticket.organization_id == org and t.estimate_minutes == 120
        assert task(ctx, p, "Second").position == 1


def test_update_task_edits_ticket_and_task(run, org):
    with run() as ctx:
        p = mk(ctx, org)
        ph = svc.add_phase(ctx, p.id, {"name": "Plan"})
        t = task(ctx, p)
        t = svc.update_task(
            ctx,
            p.id,
            t.id,
            {"title": "Renamed", "status": "resolved", "estimate_minutes": 30, "phase_id": ph.id},
        )
        assert t.ticket.subject == "Renamed" and t.ticket.status == "resolved"
        assert (t.estimate_minutes, t.phase_id) == (30, ph.id)
        with pytest.raises(NotFound):
            svc.update_task(ctx, p.id + 1000, t.id, {"title": "x"})


def test_task_rejects_bad_assignee_and_dates(run, org, make_user):
    ro = make_user("read_only", "ro@example.com")
    with run() as ctx:
        p = mk(ctx, org)
        with pytest.raises(Conflict):
            task(ctx, p, assignee_id=ro["id"])
        from datetime import date

        with pytest.raises(Conflict):
            task(ctx, p, start_date=date(2026, 2, 2), due_date=date(2026, 2, 1))


# ---- dependencies ----
def test_cycle_is_refused(run, org):
    with run() as ctx:
        p = mk(ctx, org)
        a, b, c = (task(ctx, p, n) for n in "ABC")
        svc.add_dependency(ctx, a.id, b.id)
        svc.add_dependency(ctx, b.id, c.id)
        with pytest.raises(Conflict, match="loop"):
            svc.add_dependency(ctx, c.id, a.id)
        with pytest.raises(Conflict):
            svc.add_dependency(ctx, b.id, a.id)
        with pytest.raises(Conflict):
            svc.add_dependency(ctx, a.id, a.id)
        with pytest.raises(Conflict, match="already"):
            svc.add_dependency(ctx, a.id, b.id)
        # a diamond is not a cycle
        d = task(ctx, p, "D")
        svc.add_dependency(ctx, a.id, c.id)
        svc.add_dependency(ctx, d.id, a.id)
        svc.add_dependency(ctx, d.id, c.id)
        svc.remove_dependency(ctx, b.id, c.id)
        svc.add_dependency(ctx, c.id, b.id)  # the old edge is gone, so this is now fine


def test_dependency_across_projects_is_refused(run, org):
    with run() as ctx:
        a, b = mk(ctx, org), mk(ctx, org)
        ta, tb = task(ctx, a), task(ctx, b)
        with pytest.raises(Conflict):
            svc.add_dependency(ctx, ta.id, tb.id)
        with pytest.raises(NotFound):
            svc.add_dependency(ctx, ta.id, tb.id, project_id=b.id)


def test_remove_missing_dependency(run, org):
    with run() as ctx:
        p = mk(ctx, org)
        a, b = task(ctx, p), task(ctx, p)
        with pytest.raises(NotFound):
            svc.remove_dependency(ctx, a.id, b.id)


def test_blocked_until_dependency_resolved(run, org):
    with run() as ctx:
        p = mk(ctx, org)
        a, b = task(ctx, p, "A"), task(ctx, p, "B")
        svc.add_dependency(ctx, b.id, a.id)
        rows = {r["title"]: r for r in svc.task_rows(ctx, p)}
        assert rows["B"]["blocked"] is True and rows["B"]["depends_on"] == [a.id]
        assert rows["A"]["blocked"] is False
        svc.update_task(ctx, p.id, a.id, {"status": "closed"})
        rows = {r["title"]: r for r in svc.task_rows(ctx, p)}
        assert rows["B"]["blocked"] is False


# ---- attach / detach ----
def test_attach_and_detach_ticket(run, org_ctx, make_ticket):
    org, ticket_id = org_ctx["org"], make_ticket()["id"]
    with run() as ctx:
        p = mk(ctx, org)
        assert svc.attach_ticket(ctx, p.id, ticket_id).project_id == p.id
        other = mk(ctx, org)
        with pytest.raises(Conflict):  # already in a project (this or another)
            svc.attach_ticket(ctx, other.id, ticket_id)
        with pytest.raises(Conflict):
            svc.attach_ticket(ctx, p.id, ticket_id)
        assert svc.detach_ticket(ctx, p.id, ticket_id).project_id is None
        with pytest.raises(Conflict):
            svc.detach_ticket(ctx, p.id, ticket_id)
        with pytest.raises(NotFound):
            svc.attach_ticket(ctx, p.id, 999_999)


def test_attach_other_organization_refused(run, org, make_org_with_ticket):
    _, foreign = make_org_with_ticket("Foreign")
    with run() as ctx:
        p = mk(ctx, org)
        with pytest.raises(Conflict, match="different organization"):
            svc.attach_ticket(ctx, p.id, foreign["id"])


def test_detach_task_own_ticket_refused(run, org):
    with run() as ctx:
        p = mk(ctx, org)
        t = task(ctx, p)
        with pytest.raises(Conflict, match="own ticket"):
            svc.detach_ticket(ctx, p.id, t.ticket_id)


# ---- budget vs actual ----
def test_budget_of_empty_project_is_zeros(run, org):
    with run() as ctx:
        p = mk_tm(ctx, org, 50_000)
        assert svc.budget(ctx, p.id) == {
            "estimate_minutes": 0,
            "actual_minutes": 0,
            "billable_minutes": 0,
            "cost_at_rates_cents": 0,
            "billed_cents": 0,
            "remaining_cents": 50_000,
            "over_budget": False,
        }
        draft = mk(ctx, org)
        got = svc.budget(ctx, draft.id)
        assert got["remaining_cents"] is None and got["over_budget"] is False


def test_budget_exact_cents(run, org, wt, log, owner, admin):
    with run() as ctx:
        p = mk_tm(ctx, org, 40_000)
        t1, t2 = task(ctx, p, estimate_minutes=120), task(ctx, p, estimate_minutes=60)
        t1_ticket, t2_ticket = t1.ticket_id, t2.ticket_id
        pid = p.id
    log(t1_ticket, wt["Remote"], 90)  # 1.5 h  = 225.00
    log(t2_ticket, wt["Remote"], 7)  # rounds up to 15 min = 0.25 h = 37.50
    voided = log(t2_ticket, wt["Remote"], 60)
    assert admin.post(f"/api/v1/time-entries/{voided['id']}/void").status_code == 200
    log(t2_ticket, wt["Remote"], 30, billable=False)  # worked, never billed
    with run() as ctx:
        b = svc.budget(ctx, pid)
        assert b["estimate_minutes"] == 180
        assert b["actual_minutes"] == 127 and b["billable_minutes"] == 105  # 90 + 7 + 30 worked
        assert b["cost_at_rates_cents"] == 26_250  # 1.75 h x 150.00
        assert (b["billed_cents"], b["remaining_cents"], b["over_budget"]) == (
            0,
            40_000,
            False,
        )
        rows = {r["ticket_id"]: r for r in svc.task_rows(ctx, svc.get_project(ctx, pid))}
        assert rows[t1_ticket]["actual_minutes"] == 90 and rows[t2_ticket]["actual_minutes"] == 37


def test_budget_billed_remaining_and_over_budget(run, org, wt, log, owner):
    with run() as ctx:
        p = mk_tm(ctx, org, 30_000)
        pid, tid = p.id, task(ctx, p).ticket_id
    log(tid, wt["Remote"], 240)  # 4 h = 600.00 at cost, over the 300.00 budget
    inv = {}
    for name in ("draft", "void"):
        inv[name] = owner.execute(
            text("INSERT INTO invoices (organization_id) VALUES (:o) RETURNING id"), {"o": org}
        ).scalar_one()

    def line(invoice, amount, voided=False):
        owner.execute(
            text(
                "INSERT INTO invoice_lines (invoice_id, organization_id, kind, description, "
                "quantity, unit_price_cents, amount_cents, project_id, voided) "
                "VALUES (:i, :o, 'time', 'x', 1, :a, :a, :p, :v)"
            ),
            {"i": invoice, "o": org, "a": amount, "p": pid, "v": voided},
        )

    line(inv["draft"], 12_345)
    line(inv["draft"], 5_000, voided=True)  # voided line: ignored
    line(inv["void"], 7_000)  # voided invoice: ignored
    owner.execute(
        text("UPDATE invoices SET status = 'void', number = 'PRJ-VOID-1' WHERE id = :i"),
        {"i": inv["void"]},
    )
    with run() as ctx:
        b = svc.budget(ctx, pid)
        assert b["billed_cents"] == 12_345 and b["remaining_cents"] == 17_655
        assert b["cost_at_rates_cents"] == 60_000 and b["over_budget"] is True
    line(inv["draft"], 20_000)
    with run() as ctx:
        assert svc.budget(ctx, pid)["remaining_cents"] == 0  # never negative


def test_budget_fixed_fee_has_no_remaining(run, org, wt, log):
    with run() as ctx:
        p = mk(ctx, org, billing_mode="fixed_fee", fixed_fee_cents=10_000)
        pid, tid = p.id, task(ctx, p).ticket_id
    log(tid, wt["Remote"], 60)  # 150.00 at rates, over the 100.00 fee
    with run() as ctx:
        b = svc.budget(ctx, pid)
        assert b["remaining_cents"] is None and b["over_budget"] is True


def test_budget_uses_org_rate_override(run, org, wt, log, admin):
    with run() as ctx:
        p = mk_tm(ctx, org)
        pid, tid = p.id, task(ctx, p).ticket_id
    r = admin.put(
        f"/api/v1/organizations/{org}/billing/rates/{wt['Remote']}", json={"rate_cents": 10_000}
    )
    assert r.status_code == 200, r.text
    log(tid, wt["Remote"], 60)
    with run() as ctx:
        assert svc.budget(ctx, pid)["cost_at_rates_cents"] == 10_000
