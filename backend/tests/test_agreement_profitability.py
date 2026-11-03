"""Profitability and utilisation by agreement (Plan 17-03), pinned to the cent.

Invoice lines are arranged with owner SQL on a draft invoice and then finalized through the API,
so each line's agreement and time links are exact; the reports are read as billing."""

import csv
import io
from datetime import date

import pytest
from sqlalchemy import text

from app import report_metrics as rm
from app.db import new_session, set_org_scope
from app.deps import Ctx
from app.scope import Scope
from tests.test_report_metrics import HI, LO, add_expense, add_user

P = {"from": str(LO), "to": str(HI)}


def agreement(owner, org, name, kind, cents, **cols):
    fields = dict(
        organization_id=org,
        name=name,
        type=kind,
        unit_price_cents=cents,
        start_date=date(2026, 1, 1),
        **cols,
    )
    names, marks = ", ".join(fields), ", ".join(f":{k}" for k in fields)
    return owner.execute(
        text(f"INSERT INTO agreements ({names}) VALUES ({marks}) RETURNING id"), fields
    ).scalar_one()


def entry(owner, org, ticket, user, minutes, agreement_id=None, covered=0, work_date=None):
    wt = owner.execute(text("SELECT id FROM work_types ORDER BY id LIMIT 1")).scalar_one()
    return owner.execute(
        text(
            "INSERT INTO time_entries (ticket_id, organization_id, user_id, work_type_id,"
            " work_date, minutes_actual, minutes_billable, billable, block_minutes_covered,"
            " agreement_id) VALUES (:t, :o, :u, :w, :d, :m, :m, true, :c, :a) RETURNING id"
        ),
        dict(t=ticket, o=org, u=user, w=wt, d=work_date or date(2026, 3, 5), m=minutes,
             c=covered, a=agreement_id),
    ).scalar_one()  # fmt: skip


def invoice(biller, owner, org, lines, invoice_date=date(2026, 3, 10)):
    """lines: (kind, cents, agreement_id, [time entry ids]) -> the finalized invoice id."""
    inv = biller.post(
        "/api/v1/invoices", json={"organization_id": org, "include_unbilled": False}
    ).json()
    for pos, (kind, cents, aid, entries) in enumerate(lines):
        line = owner.execute(
            text(
                "INSERT INTO invoice_lines (invoice_id, organization_id, position, kind,"
                " description, quantity, unit_price_cents, amount_cents, agreement_id)"
                " VALUES (:i, :o, :p, :k, 'x', 1, :c, :c, :a) RETURNING id"
            ),
            dict(i=inv["id"], o=org, p=pos, k=kind, c=cents, a=aid),
        ).scalar_one()
        for e in entries:
            owner.execute(
                text("UPDATE time_entries SET invoice_line_id = :l WHERE id = :e"),
                dict(l=line, e=e),
            )
    r = biller.post(
        f"/api/v1/invoices/{inv['id']}/finalize", json={"invoice_date": invoice_date.isoformat()}
    )
    assert r.status_code == 200, r.text
    return inv["id"]


@pytest.fixture
def data(biller, owner, make_org_with_ticket, make_user, company):
    flat, flat_t = make_org_with_ticket("Flat Co")
    block, block_t = make_org_with_ticket("Block Co")
    fee, _ = make_org_with_ticket("Fee Co")
    f, b, fe = flat["id"], block["id"], fee["id"]
    rated = add_user(make_user, "ap-rate@example.com", 9000, owner)  # $90/h
    norate = add_user(make_user, "ap-norate@example.com", None, owner)

    # all-inclusive flat: $100.00 a month, 120 min of attached labour at $90/h = $180.00
    a_flat = agreement(owner, f, "All you can eat", "flat", 10000, all_inclusive=True)
    entry(owner, f, flat_t["id"], rated, 120, a_flat)
    entry(owner, f, flat_t["id"], norate, 30, a_flat)  # no cost rate: counted, not costed
    entry(owner, f, flat_t["id"], rated, 999, a_flat, work_date=date(2026, 4, 2))  # out of range
    invoice(biller, owner, f, [("agreement", 10000, a_flat, [])])

    # block: $300.00 fee; 90 min attached, 30 covered by the block, 60 billed as overage $90.00
    a_block = agreement(owner, b, "Block 10h", "block", 30000, block_minutes=600)
    over = entry(owner, b, block_t["id"], rated, 90, a_block, covered=30)
    loose = entry(owner, b, block_t["id"], rated, 60)  # unattached: 'No agreement'
    mixed_b = entry(owner, b, block_t["id"], rated, 1, a_block)
    mixed_n = entry(owner, b, block_t["id"], rated, 2)
    invoice(
        biller,
        owner,
        b,
        [
            ("agreement", 30000, a_block, []),
            ("time", 9000, None, [over]),
            ("time", 4500, None, [loose]),
            ("time", 1001, None, [mixed_b, mixed_n]),  # split 1:2 by billed minutes
            ("manual", 1000, None, []),
        ],
    )
    add_expense(owner, rated, b, date(2026, 3, 9), 2500)
    voided = invoice(biller, owner, b, [("agreement", 77777, a_block, [])])
    r = biller.post(f"/api/v1/invoices/{voided}/void", json={"reason": "wrong month"})
    assert r.status_code == 200, r.text

    # an agreement with revenue but no time
    a_fee = agreement(owner, fe, "Monitoring", "flat", 20000)
    invoice(biller, owner, fe, [("agreement", 20000, a_fee, [])])
    return dict(flat=a_flat, block=a_block, fee=a_fee, flat_org=f, block_org=b, fee_org=fe)


def rows(d):
    return {(r["organization_id"], r["agreement_id"]): r for r in d["rows"]}


def test_metrics_by_agreement_to_the_cent(biller, data):
    with new_session() as db:
        set_org_scope(db, "all")
        ctx = Ctx(db=db, user=None, scope=Scope.all())
        d = rm.profitability(ctx, LO, HI, "agreement")
    by = rows(d)
    flat = by[(data["flat_org"], data["flat"])]
    assert (flat["agreement_name"], flat["agreement_type"]) == ("All you can eat", "flat")
    assert (flat["revenue_cents"], flat["labour_cost_cents"]) == (10000, 18000)
    assert flat["margin_cents"] == -8000 and flat["margin_bp"] == -8000
    assert flat["minutes_without_cost_rate"] == 30
    block = by[(data["block_org"], data["block"])]
    # fee + overage + a third of the mixed line (floor(1001 / 3) = 333)
    assert block["revenue_cents"] == 30000 + 9000 + 333
    # 90 + 1 minutes at $90/h, rounded per entry: 13,500 + 150
    assert block["labour_cost_cents"] == 13500 + 150
    none = by[(data["block_org"], None)]
    assert none["agreement_name"] == "No agreement" and none["agreement_type"] is None
    # unattached time line + 668 of the mixed line (remainder to the larger share) + manual
    assert none["revenue_cents"] == 4500 + 668 + 1000
    assert none["labour_cost_cents"] == 9000 + 300 and none["expense_cost_cents"] == 2500
    fee = by[(data["fee_org"], data["fee"])]
    assert (fee["revenue_cents"], fee["cost_cents"], fee["margin_bp"]) == (20000, 0, 10000)
    assert set(by) == {
        (data["flat_org"], data["flat"]),
        (data["block_org"], data["block"]),
        (data["block_org"], None),
        (data["fee_org"], data["fee"]),
    }  # voided invoice and out-of-range time add nothing


def test_agreement_rows_reconcile_with_the_client_view(biller, data):
    client = biller.get("/api/v1/reports/profitability", params=P).json()
    agr = biller.get("/api/v1/reports/profitability", params={**P, "group": "agreement"}).json()
    assert agr["totals"] == client["totals"]
    assert (client["group"], agr["group"]) == ("client", "agreement")
    assert {r["agreement_id"] for r in client["rows"]} == {None}
    flat = rows(agr)[(data["flat_org"], data["flat"])]
    assert (flat["agreement_name"], flat["agreement_type"]) == ("All you can eat", "flat")
    assert client["totals"]["revenue_cents"] == 10000 + 45501 + 20000
    for c in client["rows"]:
        mine = [r for r in agr["rows"] if r["organization_id"] == c["organization_id"]]
        for k in ("revenue_cents", "labour_cost_cents", "expense_cost_cents", "cost_cents"):
            assert sum(r[k] for r in mine) == c[k], k
    rev = biller.get("/api/v1/reports/revenue", params=P).json()
    assert agr["totals"]["revenue_cents"] == rev["totals"]["subtotal_cents"]


def test_profitability_csv_by_agreement(biller, data):
    r = biller.get("/api/v1/reports/profitability.csv", params={**P, "group": "agreement"})
    assert r.status_code == 200
    assert (
        "profitability-by-agreement-2026-03-01-2026-03-31.csv" in r.headers["content-disposition"]
    )
    lines = list(csv.reader(io.StringIO(r.text)))
    assert lines[0] == [
        "client",
        "agreement",
        "agreement_type",
        "revenue",
        "labour_cost",
        "goods_cost",
        "expense_cost",
        "cost",
        "margin",
        "margin_pct",
        "minutes_without_cost_rate",
        "charges_without_cost",
    ]
    assert ["Block Co", "Block 10h", "block", "393.33"] == lines[1][:4]
    assert ["Block Co", "No agreement", "", "61.68"] == lines[2][:4]
    assert lines[3][:4] + lines[3][8:10] == [
        "Fee Co", "Monitoring", "flat", "200.00", "200.00", "100.00%",
    ]  # fmt: skip
    assert lines[4][:5] + lines[4][8:11] == [
        "Flat Co", "All you can eat", "flat", "100.00", "180.00", "-80.00", "(80.00%)", "30",
    ]  # fmt: skip
    assert lines[-1][:4] == ["Total", "", "", "755.01"]
    plain = biller.get("/api/v1/reports/profitability.csv", params=P).text.splitlines()[0]
    assert plain.startswith("client,revenue,")


def test_utilisation_minutes_by_agreement(biller, data):
    r = biller.get("/api/v1/reports/utilisation.csv", params={**P, "group": "agreement"})
    assert r.status_code == 200
    lines = list(csv.reader(io.StringIO(r.text)))
    assert lines[0] == [
        "client", "agreement", "agreement_type",
        "logged_minutes", "billable_minutes", "automation_minutes",
    ]  # fmt: skip
    assert lines[1:] == [
        ["Block Co", "Block 10h", "block", "91", "91", "0"],
        ["Block Co", "No agreement", "", "62", "62", "0"],
        ["Flat Co", "All you can eat", "flat", "150", "150", "0"],
        ["Total", "", "", "303", "303", "0"],
    ]
    d = biller.get("/api/v1/reports/utilisation", params={**P, "group": "agreement"})
    assert d.status_code == 200 and d.json()["totals"]["logged_minutes"] == 303
    flat = [a for a in d.json()["agreements"] if a["agreement_id"] == data["flat"]]
    assert [(a["agreement_type"], a["logged_minutes"]) for a in flat] == [("flat", 150)]
    plain = biller.get("/api/v1/reports/utilisation", params=P).json()
    assert plain["group"] == "client" and plain["agreements"] is None


def test_unknown_group_is_422_and_tech_is_403(biller, login, data):
    for path in ("profitability", "profitability.csv", "utilisation", "utilisation.csv"):
        r = biller.get(f"/api/v1/reports/{path}", params={**P, "group": "ticket"})
        assert r.status_code == 422, path
    tech = login("tech", "ap-tech@example.com")
    for path in ("profitability", "profitability.csv", "utilisation"):
        r = tech.get(f"/api/v1/reports/{path}", params={**P, "group": "agreement"})
        assert r.status_code == 403, path
