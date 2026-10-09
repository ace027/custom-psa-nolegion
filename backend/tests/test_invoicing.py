from datetime import date, timedelta

from sqlalchemy import text

from tests.conftest import biz_today


def invoice(client, org_id, **kw):
    r = client.post("/api/invoices", json={"organization_id": org_id, **kw})
    assert r.status_code == 201, r.text
    return r.json()


def lines(inv):
    return {ln["description"]: ln for ln in inv["lines"]}


# ---- pulling unbilled time into a draft ----
def test_time_is_grouped_by_ticket_and_work_type_and_priced(
    admin, biller, org_ctx, make_ticket, log, wt
):
    org = org_ctx["org"]
    t1, t2 = make_ticket(subject="Printer down"), make_ticket(subject="VPN slow")
    log(t1["id"], wt["Remote"], 20)  # -> 30 billable min
    log(t1["id"], wt["Remote"], 15)  # -> 15 billable min   (45 total = 0.75 h)
    log(t1["id"], wt["Onsite"], 60)  # different work type => its own line
    log(t2["id"], wt["Remote"], 90)  # different ticket => its own line
    log(t2["id"], wt["Remote"], 30, billable=False)  # never billed
    inv = invoice(biller, org)
    by = lines(inv)
    remote1 = by[f"Ticket #{t1['number']}: Printer down (Remote, hours)"]
    assert (remote1["quantity"], remote1["unit_price_cents"], remote1["amount_cents"]) == (
        "0.7500",
        15000,
        11250,
    )
    onsite = by[f"Ticket #{t1['number']}: Printer down (Onsite, hours)"]
    assert (onsite["quantity"], onsite["amount_cents"], onsite["tax_rate_bp"]) == (
        "1.0000",
        20000,
        0,
    )
    remote2 = by[f"Ticket #{t2['number']}: VPN slow (Remote, hours)"]
    assert remote2["amount_cents"] == 22500 and len(inv["lines"]) == 3
    assert inv["status"] == "draft" and inv["number"] is None and inv["warnings"] == []
    assert inv["subtotal_cents"] == 11250 + 20000 + 22500 and inv["tax_cents"] == 0
    assert inv["total_cents"] == inv["subtotal_cents"]


def test_taxable_work_and_org_tax_rate_snapshot(admin, biller, org_ctx, make_ticket, log, wt):
    biller.patch(f"/api/organizations/{org_ctx['org']}/billing", json={"tax_rate_bp": 825})
    t = make_ticket()
    log(t["id"], wt["Remote"], 60)  # not taxable
    log(t["id"], wt["Onsite"], 60)  # taxable
    inv = invoice(biller, org_ctx["org"])
    rem = next(ln for ln in inv["lines"] if "Remote" in ln["description"])
    ons = next(ln for ln in inv["lines"] if "Onsite" in ln["description"])
    assert (rem["tax_rate_bp"], rem["tax_cents"]) == (0, 0)
    assert (ons["tax_rate_bp"], ons["amount_cents"], ons["tax_cents"]) == (825, 20000, 1650)
    assert inv["subtotal_cents"] == 35000 and inv["tax_cents"] == 1650
    assert inv["total_cents"] == 36650
    # changing the org's rate later does not rewrite the draft's snapshot
    biller.patch(f"/api/organizations/{org_ctx['org']}/billing", json={"tax_rate_bp": 1000})
    assert biller.get(f"/api/invoices/{inv['id']}").json()["tax_cents"] == 1650


def test_org_rate_override_beats_the_default(biller, org_ctx, make_ticket, log, wt):
    biller.put(
        f"/api/organizations/{org_ctx['org']}/billing/rates/{wt['Remote']}",
        json={"rate_cents": 9900},
    )
    t = make_ticket()
    log(t["id"], wt["Remote"], 60)
    inv = invoice(biller, org_ctx["org"])
    assert inv["lines"][0]["unit_price_cents"] == 9900 and inv["total_cents"] == 9900


def test_work_type_without_a_rate_is_never_billed_at_zero(
    admin, biller, org_ctx, make_ticket, log, wt
):
    t = make_ticket()
    unrated = next(
        w["id"] for w in admin.get("/api/work-types").json() if w["name"] == "After hours"
    )
    log(t["id"], unrated, 45)
    log(t["id"], wt["Remote"], 60)
    inv = invoice(biller, org_ctx["org"])
    assert len(inv["lines"]) == 1 and "Remote" in inv["lines"][0]["description"]
    assert len(inv["warnings"]) == 1 and "After hours" in inv["warnings"][0]
    assert "45 min" in inv["warnings"][0] and "unbilled" in inv["warnings"][0]
    # once a rate exists the left-over time can be pulled in
    admin.patch(f"/api/billing/work-types/{unrated}", json={"rate_cents": 30000})
    inv2 = biller.post(f"/api/invoices/{inv['id']}/add-unbilled").json()
    assert len(inv2["lines"]) == 2 and inv2["total_cents"] == 15000 + 22500


def test_time_on_an_invoice_is_locked_until_released(admin, biller, org_ctx, make_ticket, log, wt):
    t = make_ticket()
    e = log(t["id"], wt["Remote"], 30)
    inv = invoice(biller, org_ctx["org"])
    assert admin.patch(f"/api/time-entries/{e['id']}", json={"minutes": 5}).status_code == 409
    assert admin.post(f"/api/time-entries/{e['id']}/void").status_code == 409
    assert admin.get(f"/api/tickets/{t['id']}/time").json()[0]["invoice_line_id"]
    # removing the line releases the entry; it is editable and billable again
    assert biller.delete(f"/api/invoice-lines/{inv['lines'][0]['id']}").status_code == 204
    assert admin.patch(f"/api/time-entries/{e['id']}", json={"minutes": 45}).status_code == 200
    inv2 = invoice(biller, org_ctx["org"])
    assert inv2["lines"][0]["quantity"] == "0.7500"


def test_an_entry_is_billed_at_most_once(biller, org_ctx, make_ticket, log, wt):
    t = make_ticket()
    log(t["id"], wt["Remote"], 60)
    first = invoice(biller, org_ctx["org"])
    second = invoice(biller, org_ctx["org"])
    assert len(first["lines"]) == 1 and second["lines"] == []
    assert biller.post(f"/api/invoices/{second['id']}/add-unbilled").json()["lines"] == []


def test_voided_time_is_not_billed(admin, biller, org_ctx, make_ticket, log, wt):
    t = make_ticket()
    e = log(t["id"], wt["Remote"], 60)
    admin.post(f"/api/time-entries/{e['id']}/void")
    assert invoice(biller, org_ctx["org"])["lines"] == []


def test_time_dated_after_the_cutoff_waits(admin, biller, org_ctx, make_ticket, log, wt):
    t = make_ticket()
    log(t["id"], wt["Remote"], 60, work_date=(biz_today() + timedelta(days=5)).isoformat())
    assert invoice(biller, org_ctx["org"])["lines"] == []


# ---- product charges on invoices ----
def test_charges_become_product_lines_and_are_locked(admin, biller, org_ctx):
    p = biller.post(
        "/api/products", json={"name": "Switch", "unit_price_cents": 19999, "taxable": True}
    ).json()
    biller.patch(f"/api/organizations/{org_ctx['org']}/billing", json={"tax_rate_bp": 1000})
    c = biller.post(
        "/api/product-charges",
        json={"organization_id": org_ctx["org"], "product_id": p["id"], "quantity": "2"},
    ).json()
    inv = invoice(biller, org_ctx["org"])
    ln = inv["lines"][0]
    assert ln["kind"] == "product" and ln["amount_cents"] == 39998 and ln["tax_cents"] == 4000
    assert biller.post(f"/api/product-charges/{c['id']}/void").status_code == 409
    biller.delete(f"/api/invoice-lines/{ln['id']}")
    assert biller.post(f"/api/product-charges/{c['id']}/void").status_code == 200


# ---- editing a draft ----
def test_manual_lines_credits_and_line_edits_recalculate(admin, biller, org_ctx):
    inv = invoice(biller, org_ctx["org"])
    biller.patch(f"/api/organizations/{org_ctx['org']}/billing", json={"tax_rate_bp": 825})
    a = biller.post(
        f"/api/invoices/{inv['id']}/lines",
        json={
            "description": "Onboarding fee",
            "quantity": "1",
            "unit_price_cents": 50000,
            "taxable": True,
        },
    )
    assert a.status_code == 201
    assert (a.json()["kind"], a.json()["amount_cents"], a.json()["tax_cents"]) == (
        "manual",
        50000,
        4125,
    )
    credit = biller.post(
        f"/api/invoices/{inv['id']}/lines",
        json={
            "description": "Goodwill credit",
            "quantity": "1",
            "unit_price_cents": -10000,
            "taxable": False,
        },
    ).json()
    assert credit["amount_cents"] == -10000
    cur = biller.get(f"/api/invoices/{inv['id']}").json()
    assert (cur["subtotal_cents"], cur["tax_cents"], cur["total_cents"]) == (40000, 4125, 44125)
    edited = biller.patch(
        f"/api/invoice-lines/{a.json()['id']}",
        json={
            "quantity": "0.5",
            "unit_price_cents": 33333,
            "tax_rate_bp": 1000,
            "description": "Onboarding (half)",
        },
    ).json()
    assert (edited["amount_cents"], edited["tax_cents"]) == (16667, 1667)  # 16666.5 -> 16667
    cur = biller.get(f"/api/invoices/{inv['id']}").json()
    assert cur["subtotal_cents"] == 16667 - 10000 and cur["tax_cents"] == 1667
    assert cur["total_cents"] == cur["subtotal_cents"] + cur["tax_cents"]
    assert (
        biller.patch(f"/api/invoices/{inv['id']}", json={"memo": "PO 1234"}).json()["memo"]
        == "PO 1234"
    )
    audit = admin.get("/api/audit", params={"action": "invoice.line_update"}).json()["items"][0]
    assert audit["before"]["amount_cents"] == 50000 and audit["after"]["amount_cents"] == 16667
    assert biller.delete(f"/api/invoice-lines/{credit['id']}").status_code == 204
    assert biller.get(f"/api/invoices/{inv['id']}").json()["subtotal_cents"] == 16667


def test_only_manual_lines_may_be_negative(biller, org_ctx, make_ticket, log, wt):
    t = make_ticket()
    log(t["id"], wt["Remote"], 60)
    inv = invoice(biller, org_ctx["org"])
    line = inv["lines"][0]
    assert (
        biller.patch(f"/api/invoice-lines/{line['id']}", json={"quantity": "-1"}).status_code == 409
    )
    assert (
        biller.patch(f"/api/invoice-lines/{line['id']}", json={"unit_price_cents": -5}).status_code
        == 409
    )
    assert (
        biller.patch(f"/api/invoice-lines/{line['id']}", json={"quantity": "1.25"}).json()[
            "amount_cents"
        ]
        == 18750
    )  # adjusting hours in review is allowed


def test_draft_endpoint_errors(biller):
    assert biller.get("/api/invoices/999").status_code == 404
    assert biller.patch("/api/invoices/999", json={"memo": "x"}).status_code == 404
    assert (
        biller.post(
            "/api/invoices/999/lines", json={"description": "x", "unit_price_cents": 1}
        ).status_code
        == 404
    )
    assert biller.post("/api/invoices/999/add-unbilled").status_code == 404
    assert biller.patch("/api/invoice-lines/999", json={"description": "x"}).status_code == 404
    assert biller.delete("/api/invoice-lines/999").status_code == 404
    assert biller.post("/api/invoices", json={"organization_id": 999}).status_code == 404
    assert biller.post("/api/invoices/999/finalize").status_code == 404
    assert biller.post("/api/invoices/999/void").status_code == 404
    assert biller.get("/api/invoices/999/pdf").status_code == 404


# ---- finalize ----
def finalize(client, inv_id, **kw):
    return client.post(f"/api/invoices/{inv_id}/finalize", json=kw)


def simple_invoice(biller, org_id, cents=10000):
    inv = invoice(biller, org_id, include_unbilled=False)
    biller.post(
        f"/api/invoices/{inv['id']}/lines",
        json={"description": "Consulting", "quantity": "1", "unit_price_cents": cents},
    )
    return inv


def test_finalize_needs_a_company_name_and_lines(admin, biller, org_ctx, company):
    empty = invoice(biller, org_ctx["org"], include_unbilled=False)
    assert finalize(biller, empty["id"]).status_code == 409  # no lines
    admin.patch("/api/settings", json={"company_name": ""})
    inv = simple_invoice(biller, org_ctx["org"])
    r = finalize(biller, inv["id"])
    assert r.status_code == 409 and "company name" in r.json()["detail"]


def test_finalize_assigns_gap_free_numbers_dates_and_snapshots(admin, biller, org_ctx, company):
    biller.patch(f"/api/organizations/{org_ctx['org']}/billing", json={"payment_terms_days": 15})
    admin.patch(f"/api/organizations/{org_ctx['org']}", json={"billing_address": "9 Elm St"})
    a, b = simple_invoice(biller, org_ctx["org"]), simple_invoice(biller, org_ctx["org"], 500)
    year = biz_today().year
    fa = finalize(biller, a["id"], invoice_date="2025-03-10").json()
    assert fa["number"] == "INV-2025-0001" and fa["status"] == "final"
    assert fa["invoice_date"] == "2025-03-10" and fa["due_date"] == "2025-03-25"
    assert fa["terms_days"] == 15 and fa["finalized_at"]
    fb = finalize(biller, b["id"], invoice_date="2025-03-11").json()
    assert fb["number"] == "INV-2025-0002"
    c = simple_invoice(biller, org_ctx["org"])
    assert finalize(biller, c["id"]).json()["number"] == f"INV-{year}-0001"  # counters are per year
    assert finalize(biller, c["id"]).status_code == 409  # already final
    row = biller.get("/api/invoices", params={"status": "final", "limit": 1}).json()
    assert row["total"] == 3 and len(row["items"]) == 1
    assert admin.get("/api/audit", params={"action": "invoice.finalize"}).json()["total"] == 3


def test_a_finalized_invoice_is_immutable_through_the_api(biller, org_ctx, company):
    inv = simple_invoice(biller, org_ctx["org"])
    finalize(biller, inv["id"])
    line = biller.get(f"/api/invoices/{inv['id']}").json()["lines"][0]
    assert biller.patch(f"/api/invoices/{inv['id']}", json={"memo": "x"}).status_code == 409
    assert (
        biller.post(
            f"/api/invoices/{inv['id']}/lines", json={"description": "x", "unit_price_cents": 1}
        ).status_code
        == 409
    )
    assert (
        biller.patch(f"/api/invoice-lines/{line['id']}", json={"quantity": "2"}).status_code == 409
    )
    assert biller.delete(f"/api/invoice-lines/{line['id']}").status_code == 409
    assert biller.post(f"/api/invoices/{inv['id']}/add-unbilled").status_code == 409


def test_a_negative_total_cannot_be_finalized(biller, org_ctx, company):
    inv = simple_invoice(biller, org_ctx["org"], cents=1000)
    biller.post(
        f"/api/invoices/{inv['id']}/lines",
        json={"description": "Big credit", "quantity": "1", "unit_price_cents": -5000},
    )
    r = finalize(biller, inv["id"])
    assert r.status_code == 409 and "negative" in r.json()["detail"]


def test_snapshots_keep_old_invoices_stable(admin, biller, org_ctx, company):
    inv = simple_invoice(biller, org_ctx["org"])
    finalize(biller, inv["id"])
    admin.patch(f"/api/organizations/{org_ctx['org']}", json={"name": "Renamed Corp"})
    admin.patch("/api/settings", json={"company_name": "New Company Name"})
    pdf = biller.get(f"/api/invoices/{inv['id']}/pdf").content
    assert b"Acme Corp" in pdf and b"Renamed Corp" not in pdf  # bill-to frozen at finalize
    assert b"Acme MSP LLC" in pdf and b"New Company Name" not in pdf


# ---- void ----
def test_voiding_a_final_invoice_needs_a_reason_keeps_the_number_and_releases_work(
    admin, biller, org_ctx, company, make_ticket, log, wt
):
    t = make_ticket()
    e = log(t["id"], wt["Remote"], 60)
    c = biller.post(
        "/api/product-charges",
        json={"organization_id": org_ctx["org"], "description": "Cable", "unit_price_cents": 900},
    ).json()
    inv = invoice(biller, org_ctx["org"])
    finalize(biller, inv["id"])
    assert biller.post(f"/api/invoices/{inv['id']}/void", json={}).status_code == 409
    assert biller.post(f"/api/invoices/{inv['id']}/void", json={"reason": "  "}).status_code == 409
    v = biller.post(f"/api/invoices/{inv['id']}/void", json={"reason": "Wrong client"})
    assert v.status_code == 200 and v.json()["status"] == "void"
    assert v.json()["number"] == f"INV-{biz_today().year}-0001"  # the number is never reused
    assert v.json()["void_reason"] == "Wrong client"
    assert (
        biller.post(f"/api/invoices/{inv['id']}/void", json={"reason": "again"}).status_code == 409
    )
    # the time and the charge can be billed again
    assert admin.get(f"/api/tickets/{t['id']}/time").json()[0]["invoice_line_id"] is None
    assert (
        biller.get("/api/product-charges", params={"unbilled_only": True}).json()[0]["id"]
        == c["id"]
    )
    again = invoice(biller, org_ctx["org"])
    assert len(again["lines"]) == 2
    assert finalize(biller, again["id"]).json()["number"] == f"INV-{biz_today().year}-0002"
    assert e["id"]


def test_voiding_a_draft_needs_no_reason_and_gets_no_number(biller, org_ctx):
    inv = simple_invoice(biller, org_ctx["org"])
    v = biller.post(f"/api/invoices/{inv['id']}/void").json()
    assert v["status"] == "void" and v["number"] is None


# ---- PDF ----
def test_pdf_for_a_final_invoice(biller, org_ctx, company):
    inv = simple_invoice(biller, org_ctx["org"], cents=123456)
    finalize(biller, inv["id"], invoice_date="2026-03-10")
    r = biller.get(f"/api/invoices/{inv['id']}/pdf")
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert r.headers["content-disposition"] == 'attachment; filename="INV-2026-0001.pdf"'
    assert r.content.startswith(b"%PDF")
    for needle in (
        b"INV-2026-0001",
        b"Acme MSP LLC",
        b"Acme Corp",
        b"Consulting",
        b"$1,234.56",
        b"2026-04-09",
        b"Net 30",
        b"Pay by ACH within terms.",
    ):
        assert needle in r.content, needle
    assert b"DRAFT" not in r.content and b"VOID" not in r.content


def test_pdf_for_draft_and_void_are_marked(biller, org_ctx, company):
    inv = simple_invoice(biller, org_ctx["org"])
    draft = biller.get(f"/api/invoices/{inv['id']}/pdf")
    assert b"DRAFT" in draft.content and b"assigned when finalized" in draft.content
    assert draft.headers["content-disposition"] == f'attachment; filename="DRAFT-{inv["id"]}.pdf"'
    finalize(biller, inv["id"])
    biller.post(f"/api/invoices/{inv['id']}/void", json={"reason": "Duplicate"})
    void = biller.get(f"/api/invoices/{inv['id']}/pdf").content
    assert b"VOID" in void and b"Voided: Duplicate" in void


def test_pdf_escapes_markup_in_descriptions_and_paginates(biller, org_ctx, company):
    inv = invoice(biller, org_ctx["org"], include_unbilled=False, memo="<b>bold</b> & more")
    biller.post(
        f"/api/invoices/{inv['id']}/lines",
        json={"description": "<script>alert(1)</script> & <i>x</i>", "unit_price_cents": 100},
    )
    for i in range(60):
        biller.post(
            f"/api/invoices/{inv['id']}/lines",
            json={"description": f"Line {i}", "unit_price_cents": 100 + i},
        )
    r = biller.get(f"/api/invoices/{inv['id']}/pdf")
    assert r.status_code == 200 and r.content.count(b"/Type /Page\n") >= 2
    # the tags are drawn as visible characters "<" "script" ">" (escaped, never interpreted)
    assert b"(<) Tj (script) Tj (>) Tj (alert\\(1\\)) Tj" in r.content


# ---- the invariant that matters: lines always add up ----
def test_invoice_totals_always_equal_the_sum_of_lines(admin, biller, org_ctx, company):
    import random

    rng = random.Random(1)
    biller.patch(f"/api/organizations/{org_ctx['org']}/billing", json={"tax_rate_bp": 825})
    inv = invoice(biller, org_ctx["org"], include_unbilled=False)
    for i in range(40):
        biller.post(
            f"/api/invoices/{inv['id']}/lines",
            json={
                "description": f"L{i}",
                "quantity": str(rng.randint(1, 80) / 4),
                "unit_price_cents": rng.randint(1, 99999),
                "taxable": rng.random() < 0.6,
            },
        )
    cur = biller.get(f"/api/invoices/{inv['id']}").json()
    assert cur["subtotal_cents"] == sum(ln["amount_cents"] for ln in cur["lines"])
    assert cur["tax_cents"] == sum(ln["tax_cents"] for ln in cur["lines"])
    assert cur["total_cents"] == cur["subtotal_cents"] + cur["tax_cents"]
    final = finalize(biller, inv["id"]).json()
    assert final["total_cents"] == cur["total_cents"]


def test_dates_default_to_today_in_the_business_timezone(biller, org_ctx, company):
    inv = simple_invoice(biller, org_ctx["org"])
    f = finalize(biller, inv["id"]).json()
    assert f["invoice_date"] == biz_today().isoformat()
    assert date.fromisoformat(f["due_date"]) == biz_today() + timedelta(days=30)


def test_database_owner_can_still_see_invoices_for_operations(owner, biller, org_ctx):
    simple_invoice(biller, org_ctx["org"])
    assert owner.execute(text("SELECT count(*) FROM invoices")).scalar_one() == 1
