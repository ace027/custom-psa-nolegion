from datetime import date

import pytest
from sqlalchemy import text

from tests.conftest import biz_today


def period(offset=0):
    t = biz_today()
    m = t.month - 1 + offset
    return f"{t.year + m // 12}-{m % 12 + 1:02d}"


def agreement(client, org, **kw):
    body = {
        "organization_id": org,
        "name": "Managed Services",
        "type": "per_user",
        "unit_price_cents": 1200,
        "quantity": 25,
        "start_date": "2020-01-01",
        **kw,
    }
    r = client.post("/api/agreements", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def start_run(client, p=None):
    r = client.post("/api/billing-runs", json={"period": p or period()})
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture
def two_clients(admin, biller, make_org, make_org_with_ticket, log, wt, company):
    """Alpha (agreement + time + product) and Beta (agreement only), Gamma (nothing billable)."""
    alpha, t_alpha = make_org_with_ticket("Alpha Co")
    beta = make_org("Beta Co")
    make_org("Gamma Co")
    agreement(biller, alpha["id"])
    agreement(biller, beta["id"], type="flat", unit_price_cents=250000, name="Flat Fee")
    log(t_alpha["id"], wt["Remote"], 60)
    biller.post(
        "/api/product-charges",
        json={"organization_id": alpha["id"], "description": "USB hub", "unit_price_cents": 2500},
    )
    return {"alpha": alpha["id"], "beta": beta["id"], "ticket": t_alpha}


# ---- generation ----
def test_run_builds_one_draft_per_client_with_billables(admin, biller, two_clients):
    run = start_run(biller)
    assert run["status"] == "draft" and run["invoice_count"] == 2
    names = sorted(i["organization_name"] for i in run["invoices"])
    assert names == ["Alpha Co", "Beta Co"]  # Gamma has nothing billable: no invoice
    by = {i["organization_name"]: i for i in run["invoices"]}
    assert by["Alpha Co"]["status"] == "draft" and by["Alpha Co"]["number"] is None
    alpha = biller.get(f"/api/invoices/{by['Alpha Co']['id']}").json()
    kinds = sorted(ln["kind"] for ln in alpha["lines"])
    assert kinds == ["agreement", "product", "time"]
    ag = next(ln for ln in alpha["lines"] if ln["kind"] == "agreement")
    assert ag["quantity"] == "25.0000" and ag["unit_price_cents"] == 1200
    assert ag["amount_cents"] == 30000 and ag["agreement_id"] and ag["period_start"]
    assert "Managed Services: 25 users x $12.00" in ag["description"]
    assert alpha["total_cents"] == 30000 + 15000 + 2500
    beta = biller.get(f"/api/invoices/{by['Beta Co']['id']}").json()
    assert (
        beta["lines"][0]["description"].startswith("Flat Fee (") and beta["total_cents"] == 250000
    )
    assert run["total_cents"] == alpha["total_cents"] + beta["total_cents"]
    assert alpha["billing_run_id"] == run["id"] and alpha["period_start"] == run["period_start"]
    assert admin.get("/api/audit", params={"action": "billing_run.create"}).json()["total"] == 1


def test_quantity_is_snapshotted_at_run_time(biller, two_clients):
    run = start_run(biller)
    a = biller.get("/api/agreements", params={"organization_id": two_clients["alpha"]}).json()[0]
    biller.patch(f"/api/agreements/{a['id']}", json={"quantity": 99})
    alpha = next(i for i in run["invoices"] if i["organization_name"] == "Alpha Co")
    line = next(
        ln
        for ln in biller.get(f"/api/invoices/{alpha['id']}").json()["lines"]
        if ln["kind"] == "agreement"
    )
    assert line["quantity"] == "25.0000"


def test_agreement_inclusion_rules(biller, make_org, company):
    p = period()
    start = date.fromisoformat(p + "-01")
    end_of_month = date(start.year + (start.month == 12), start.month % 12 + 1, 1)
    org = {n: make_org(n)["id"] for n in ("Mid", "Ended", "Future", "Zero", "EndsInPeriod")}
    agreement(biller, org["Mid"], start_date=start.replace(day=15).isoformat())  # billed in FULL
    agreement(biller, org["Ended"], end_date="2020-12-31")
    agreement(biller, org["Future"], start_date=end_of_month.isoformat())
    agreement(biller, org["Zero"], quantity=0)
    agreement(biller, org["EndsInPeriod"], end_date=start.replace(day=10).isoformat())
    run = start_run(biller, p)
    billed = {
        i["organization_name"]: i["total_cents"] for i in run["invoices"] if i["status"] == "draft"
    }
    assert billed == {"Mid": 30000, "EndsInPeriod": 30000}  # no proration: manual adjust in review
    assert any("Zero" in w and "quantity 0" in w for w in run["warnings"])


def test_time_without_a_rate_leaves_a_visible_warning_not_a_zero_line(
    admin, biller, make_org_with_ticket, log, company
):
    org, t = make_org_with_ticket("Unrated Co")
    unrated = next(w["id"] for w in admin.get("/api/work-types").json() if w["name"] == "Remote")
    log(t["id"], unrated, 30)
    run = start_run(biller)
    assert run["invoice_count"] == 0 and run["invoices"][0]["status"] == "void"
    assert any("Unrated Co" in w and "Remote" in w and "unbilled" in w for w in run["warnings"])
    assert (
        biller.post(f"/api/billing-runs/{run['id']}/review").status_code == 409
    )  # nothing to review


def test_archived_organizations_are_skipped_with_a_warning(admin, biller, two_clients):
    admin.post(f"/api/organizations/{two_clients['beta']}/archive")
    run = start_run(biller)
    assert [i["organization_name"] for i in run["invoices"]] == ["Alpha Co"]
    assert any("Beta Co is archived" in w for w in run["warnings"])


# ---- one run per month: no double billing ----
def test_a_month_can_only_be_run_once_until_cancelled(biller, two_clients):
    run = start_run(biller)
    dup = biller.post("/api/billing-runs", json={"period": period()})
    assert dup.status_code == 409 and "already exists" in dup.json()["detail"]
    assert biller.post(f"/api/billing-runs/{run['id']}/cancel").json()["status"] == "cancelled"
    again = start_run(biller)
    assert again["id"] != run["id"] and again["invoice_count"] == 2


def test_database_refuses_a_second_live_line_for_the_same_agreement_period(
    owner, biller, two_clients
):
    start_run(biller)
    row = owner.execute(
        text(
            "SELECT invoice_id, organization_id, agreement_id, period_start "
            "FROM invoice_lines WHERE kind = 'agreement' LIMIT 1"
        )
    ).one()
    insert = text(
        "INSERT INTO invoice_lines (invoice_id, organization_id, kind, description, "
        "quantity, unit_price_cents, amount_cents, agreement_id, period_start) "
        "VALUES (:i, :o, 'agreement', 'dup', 1, 1, 1, :a, :p)"
    )
    with pytest.raises(Exception, match="uq_invoice_lines_agreement_period"):
        owner.execute(
            insert,
            {
                "i": row.invoice_id,
                "o": row.organization_id,
                "a": row.agreement_id,
                "p": row.period_start,
            },
        )


def test_period_validation(biller, two_clients):
    assert biller.post("/api/billing-runs", json={"period": "2026-13"}).status_code == 422
    assert biller.post("/api/billing-runs", json={"period": "202610"}).status_code == 422
    far = biller.post("/api/billing-runs", json={"period": period(3)})
    assert far.status_code == 409 and "next month" in far.json()["detail"]
    assert (
        biller.post("/api/billing-runs", json={"period": period(1)}).status_code == 201
    )  # in advance


# ---- review, finalize ----
def test_finalize_requires_review_then_numbers_in_client_order(admin, biller, two_clients):
    run = start_run(biller)
    assert biller.post(f"/api/billing-runs/{run['id']}/finalize").status_code == 409
    reviewed = biller.post(f"/api/billing-runs/{run['id']}/review").json()
    assert reviewed["status"] == "reviewed" and reviewed["reviewed_at"]
    assert biller.post(f"/api/billing-runs/{run['id']}/review").status_code == 409  # not a draft
    done = biller.post(
        f"/api/billing-runs/{run['id']}/finalize", json={"invoice_date": "2025-12-01"}
    ).json()
    assert done["status"] == "finalized" and done["finalized_at"]
    by = {i["organization_name"]: i for i in done["invoices"]}
    assert by["Alpha Co"]["number"] == "INV-2025-0001"  # alphabetical, gap-free
    assert by["Beta Co"]["number"] == "INV-2025-0002"
    assert all(i["status"] == "final" and i["due_date"] == "2025-12-31" for i in done["invoices"])
    assert biller.post(f"/api/billing-runs/{run['id']}/cancel").status_code == 409
    assert biller.post(f"/api/billing-runs/{run['id']}/finalize").status_code == 409
    listed = biller.get("/api/billing-runs").json()
    assert listed[0]["status"] == "finalized" and listed[0]["invoice_count"] == 2
    assert biller.get(f"/api/billing-runs/{run['id']}").json()["invoices"][0]["number"]
    actions = {
        a["action"]
        for a in admin.get("/api/audit", params={"action": "billing_run."}).json()["items"]
    }
    assert {"billing_run.create", "billing_run.review", "billing_run.finalize"} <= actions


def test_an_invoice_in_an_open_run_cannot_be_finalized_alone(biller, two_clients):
    run = start_run(biller)
    r = biller.post(f"/api/invoices/{run['invoices'][0]['id']}/finalize")
    assert r.status_code == 409 and "billing run" in r.json()["detail"]


def test_editing_a_draft_undoes_the_review(biller, two_clients):
    run = start_run(biller)
    biller.post(f"/api/billing-runs/{run['id']}/review")
    inv = run["invoices"][0]
    biller.post(
        f"/api/invoices/{inv['id']}/lines",
        json={"description": "Adjustment", "quantity": "1", "unit_price_cents": -100},
    )
    assert biller.get(f"/api/billing-runs/{run['id']}").json()["status"] == "draft"
    assert biller.post(f"/api/billing-runs/{run['id']}/finalize").status_code == 409
    assert biller.post(f"/api/billing-runs/{run['id']}/review").status_code == 200


@pytest.mark.parametrize("edit", ["update", "delete", "memo", "void", "add_unbilled"])
def test_every_kind_of_draft_change_invalidates_the_review(admin, biller, two_clients, edit):
    run = start_run(biller)
    inv = next(i for i in run["invoices"] if i["organization_name"] == "Alpha Co")
    detail = biller.get(f"/api/invoices/{inv['id']}").json()
    biller.post(f"/api/billing-runs/{run['id']}/review")
    line = detail["lines"][0]
    {
        "update": lambda: biller.patch(
            f"/api/invoice-lines/{line['id']}", json={"description": "x"}
        ),
        "delete": lambda: biller.delete(f"/api/invoice-lines/{line['id']}"),
        "memo": lambda: biller.patch(f"/api/invoices/{inv['id']}", json={"memo": "hello"}),
        "void": lambda: biller.post(f"/api/invoices/{inv['id']}/void"),
        "add_unbilled": lambda: biller.post(f"/api/invoices/{inv['id']}/add-unbilled"),
    }[edit]()
    assert biller.get(f"/api/billing-runs/{run['id']}").json()["status"] == "draft"
    assert any(
        a["action"] == "billing_run.review_invalidated"
        for a in admin.get("/api/audit", params={"action": "billing_run."}).json()["items"]
    )


def test_finalize_is_all_or_nothing(admin, owner, biller, two_clients):
    run = start_run(biller)
    beta = next(i for i in run["invoices"] if i["organization_name"] == "Beta Co")
    biller.post(
        f"/api/invoices/{beta['id']}/lines",
        json={"description": "Oversized credit", "quantity": "1", "unit_price_cents": -999999},
    )
    biller.post(f"/api/billing-runs/{run['id']}/review")
    r = biller.post(f"/api/billing-runs/{run['id']}/finalize")
    assert (
        r.status_code == 409
        and "Beta Co" in r.json()["detail"]
        and "negative" in r.json()["detail"]
    )
    state = biller.get(f"/api/billing-runs/{run['id']}").json()
    assert state["status"] == "reviewed"
    assert all(i["status"] == "draft" and i["number"] is None for i in state["invoices"])
    assert (
        owner.execute(text("SELECT count(*) FROM invoice_counters")).scalar_one() == 0
    )  # no burned numbers
    # fix it and finalize: numbering starts at 1 with no gap
    line = next(
        ln
        for ln in biller.get(f"/api/invoices/{beta['id']}").json()["lines"]
        if ln["unit_price_cents"] < 0
    )
    biller.delete(f"/api/invoice-lines/{line['id']}")
    biller.post(f"/api/billing-runs/{run['id']}/review")
    done = biller.post(f"/api/billing-runs/{run['id']}/finalize").json()
    assert sorted(i["number"][-4:] for i in done["invoices"]) == ["0001", "0002"]


def test_cancel_frees_the_month_and_releases_everything(admin, biller, two_clients):
    run = start_run(biller)
    biller.post(f"/api/billing-runs/{run['id']}/review")
    cancelled = biller.post(f"/api/billing-runs/{run['id']}/cancel").json()
    assert cancelled["status"] == "cancelled" and cancelled["invoice_count"] == 0
    assert all(i["status"] == "void" for i in cancelled["invoices"])
    assert (
        admin.get(f"/api/tickets/{two_clients['ticket']['id']}/time").json()[0]["invoice_line_id"]
        is None
    )
    assert len(biller.get("/api/product-charges", params={"unbilled_only": True}).json()) == 1
    assert start_run(biller)["invoice_count"] == 2  # everything is billable again


def test_time_logged_after_generation_joins_via_add_unbilled(admin, biller, two_clients, log, wt):
    run = start_run(biller)
    alpha = next(i for i in run["invoices"] if i["organization_name"] == "Alpha Co")
    log(two_clients["ticket"]["id"], wt["Onsite"], 30)
    assert len(biller.get(f"/api/invoices/{alpha['id']}").json()["lines"]) == 3
    added = biller.post(f"/api/invoices/{alpha['id']}/add-unbilled").json()
    assert len(added["lines"]) == 4


def test_void_a_finalized_run_invoice_afterwards(biller, two_clients):
    run = start_run(biller)
    biller.post(f"/api/billing-runs/{run['id']}/review")
    done = biller.post(f"/api/billing-runs/{run['id']}/finalize").json()
    inv = done["invoices"][0]
    assert (
        biller.post(f"/api/invoices/{inv['id']}/void", json={"reason": "Client disputed"}).json()[
            "status"
        ]
        == "void"
    )
    after = biller.get(f"/api/billing-runs/{run['id']}").json()
    assert after["status"] == "finalized" and after["invoice_count"] == 1
    # the month is still closed: a fix goes on a manual invoice, never a second run
    assert biller.post("/api/billing-runs", json={"period": period()}).status_code == 409


def test_run_endpoint_errors_and_permissions(login, biller, two_clients):
    for path in ("review", "finalize", "cancel"):
        assert biller.post(f"/api/billing-runs/999/{path}").status_code == 404
    assert biller.get("/api/billing-runs/999").status_code == 404
    run = start_run(biller)
    tech, ro = login("tech"), login("read_only")
    assert tech.post("/api/billing-runs", json={"period": period(1)}).status_code == 403
    assert ro.get("/api/billing-runs").status_code == 200
    assert ro.get(f"/api/billing-runs/{run['id']}").status_code == 200
    for c in (tech, ro):
        assert c.post(f"/api/billing-runs/{run['id']}/review").status_code == 403
        assert c.post(f"/api/billing-runs/{run['id']}/finalize").status_code == 403
        assert c.post(f"/api/billing-runs/{run['id']}/cancel").status_code == 403
    assert biller.get("/api/invoices", params={"billing_run_id": run["id"]}).json()["total"] == 2
