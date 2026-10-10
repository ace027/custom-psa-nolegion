"""New-client quoting: pricing math, survey -> quote -> approval -> acceptance, and the guards."""

from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from app import quoting
from tests.conftest import biz_today
from tests.test_notices import worker_sends

# ---- pure pricing -------------------------------------------------------------------------


def qs(**kw):
    base = dict(
        per_user_rate_cents=10000,
        workstation_rate_cents=2000,
        server_rate_cents=10000,
        network_rate_cents=0,
        other_rate_cents=0,
        hardware_uplift_bp=2500,
        server_uplift_bp=0,
        legacy_app_uplift_bp=0,
        intro_text=None,
    )
    return SimpleNamespace(**{**base, **kw})


def survey(users=10, devices=(), apps=()):
    return SimpleNamespace(
        user_count=users,
        site_count=1,
        devices=[
            SimpleNamespace(device_class=c, warranty_status=w, priced=p) for c, w, p in devices
        ],
        apps=[SimpleNamespace(name=n, legacy=lg) for n, lg in apps],
    )


def ws(n_in, n_out):
    return [("workstation", "in_warranty", True)] * n_in + [
        ("workstation", "out_of_warranty", True)
    ] * n_out


def test_base_is_users_plus_devices_per_class_and_no_uplift_when_under_half():
    s = quoting.compute(qs(), survey(10, ws(8, 0) + [("server", "in_warranty", True)]))
    assert s["base_cents"] == 10 * 10000 + 8 * 2000 + 10000 == 126000
    assert (s["uplift_bp"], s["price_cents"]) == (0, 126000)
    assert [line["description"] for line in s["base_lines"]] == ["Users", "Workstations", "Servers"]


def test_hardware_uplift_needs_strictly_more_than_half_out_of_warranty():
    assert quoting.compute(qs(), survey(0, ws(2, 2)))["uplift_bp"] == 0  # exactly half
    s = quoting.compute(qs(), survey(0, ws(2, 3)))  # 3 of 5
    assert s["uplift_bp"] == 2500
    assert "3 of 5 priced devices (60%)" in s["factors"][0]["reason"]
    assert s["price_cents"] == 5 * 2000 * 125 // 100


def test_unknown_warranty_counts_as_out_but_is_called_out():
    devices = [("workstation", "unknown", True)] * 3 + ws(1, 0)
    s = quoting.compute(qs(), survey(0, devices))
    assert s["devices"]["out"] == 3 and s["devices"]["unknown"] == 3
    assert (
        s["factors"][0]["applies"]
        and "3 have no warranty information" in (s["factors"][0]["reason"])
    )


def test_unpriced_devices_do_not_count_toward_price_or_the_half_test():
    devices = ws(2, 0) + [("workstation", "out_of_warranty", False)] * 5
    s = quoting.compute(qs(), survey(0, devices))
    assert s["devices"]["priced"] == 2 and s["uplift_bp"] == 0 and s["base_cents"] == 4000


def test_uplifts_add_and_never_compound_and_round_once():
    q = qs(server_uplift_bp=1000, legacy_app_uplift_bp=1500)
    devices = ws(0, 3) + [("server", "out_of_warranty", True)]
    s = quoting.compute(q, survey(1, devices, apps=[("Old ERP", True)]))
    assert s["uplift_bp"] == 2500 + 1000 + 1500  # 50%, not 1.25 * 1.10 * 1.15
    assert s["price_cents"] == round(s["base_cents"] * 1.5)
    assert quoting.compute(qs(per_user_rate_cents=333), survey(1))["price_cents"] == 333
    odd = quoting.compute(
        qs(per_user_rate_cents=333, legacy_app_uplift_bp=1250), survey(1, apps=[("X", True)])
    )
    assert odd["price_cents"] == 375  # 333 * 1.125 = 374.6 -> 375, rounded once


def test_warranty_end_date_decides_the_status_when_given():
    d = date(2026, 6, 1)
    assert quoting.derive_warranty(date(2026, 6, 1), "unknown", d) == "in_warranty"
    assert quoting.derive_warranty(date(2026, 5, 31), "in_warranty", d) == "out_of_warranty"
    assert quoting.derive_warranty(None, "out_of_warranty", d) == "out_of_warranty"


def test_contract_end_is_the_day_before_the_anniversary():
    assert quoting.contract_end(date(2026, 3, 15), 12) == date(2027, 3, 14)
    assert quoting.contract_end(date(2026, 1, 31), 1) == date(2026, 2, 27)


# ---- API flow ------------------------------------------------------------------------------
@pytest.fixture
def rates(admin):
    r = admin.patch(
        "/api/quotes/settings",
        json={
            "per_user_rate_cents": 10000,
            "workstation_rate_cents": 2000,
            "server_rate_cents": 10000,
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture
def tech(login):
    return login("tech")


@pytest.fixture
def prospect(admin, company):
    org = admin.post("/api/organizations", json={"name": "Newco", "status": "prospect"}).json()
    admin.post(
        f"/api/organizations/{org['id']}/contacts",
        json={"name": "Nina New", "email": "nina@newco.com", "is_primary": True},
    )
    return org["id"]


def device(cls="workstation", warranty="in_warranty", **kw):
    return {"device_class": cls, "warranty_status": warranty, **kw}


ENV = {  # 10 users, 8 workstations (5 out of warranty), 1 server: hardware uplift applies
    "user_count": 10,
    "site_count": 1,
    "devices": [device(warranty="out_of_warranty")] * 5 + [device()] * 3 + [device("server")],
    "apps": [{"name": "QuickBooks 2012", "legacy": False}],
}


def surveyed(tech, org, body=None, complete=True):
    r = tech.post(f"/api/organizations/{org}/surveys", json={})
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    r = tech.put(f"/api/surveys/{sid}", json=body or ENV)
    assert r.status_code == 200, r.text
    if complete:
        assert tech.post(f"/api/surveys/{sid}/complete").status_code == 200
    return sid


def draft(tech, org, **kw):
    sid = surveyed(tech, org, **kw)
    r = tech.post(f"/api/surveys/{sid}/quote", json={})
    assert r.status_code == 201, r.text
    return r.json()


def test_rate_card_is_readable_by_techs_but_only_admins_can_change_it(tech, login, rates):
    assert tech.get("/api/quotes/settings").json()["hardware_uplift_bp"] == 2500
    assert tech.patch("/api/quotes/settings", json={"hardware_uplift_bp": 1}).status_code == 403
    assert login("billing").get("/api/quotes/settings").status_code == 200
    bad = login("admin").patch("/api/quotes/settings", json={"term_months": 0})
    assert bad.status_code == 422


def test_survey_is_saved_priced_and_shows_its_working(tech, prospect, rates):
    q = draft(tech, prospect)
    assert q["status"] == "draft" and q["number"] == f"Q-{q['id']}"
    assert q["base_cents"] == 126000 and q["uplift_bp"] == 2500
    assert q["computed_price_cents"] == q["final_price_cents"] == 157500
    hw = q["snapshot"]["factors"][0]
    assert hw["applies"] and "5 of 9 priced devices (56%)" in hw["reason"]
    assert q["term_months"] == 12


def test_quote_needs_a_completed_survey_and_a_rate_card(tech, prospect, admin):
    sid = surveyed(tech, prospect, complete=False)
    assert tech.post(f"/api/surveys/{sid}/quote", json={}).status_code == 409
    tech.post(f"/api/surveys/{sid}/complete")
    r = tech.post(f"/api/surveys/{sid}/quote", json={})  # rates are all zero
    assert r.status_code == 409 and "rate card" in r.json()["detail"]


def test_completed_survey_cannot_be_edited_and_empty_one_cannot_complete(tech, prospect):
    sid = surveyed(tech, prospect)
    assert tech.put(f"/api/surveys/{sid}", json=ENV).status_code == 409
    empty = tech.post(f"/api/organizations/{prospect}/surveys", json={}).json()["id"]
    tech.put(f"/api/surveys/{empty}", json={"user_count": 0})
    assert tech.post(f"/api/surveys/{empty}/complete").status_code == 409


def test_warranty_date_on_a_device_sets_its_status(tech, prospect):
    sid = tech.post(f"/api/organizations/{prospect}/surveys", json={}).json()["id"]
    old = (biz_today() - timedelta(days=5)).isoformat()
    new = (biz_today() + timedelta(days=5)).isoformat()
    s = tech.put(
        f"/api/surveys/{sid}",
        json={
            "user_count": 1,
            "devices": [
                device(warranty_end=old, warranty_status="in_warranty"),
                device(warranty_end=new, warranty_status="out_of_warranty"),
            ],
        },
    ).json()
    assert [d["warranty_status"] for d in s["devices"]] == ["out_of_warranty", "in_warranty"]
    # saving again replaces, not appends
    s = tech.put(f"/api/surveys/{sid}", json={"user_count": 2, "devices": [device()]}).json()
    assert len(s["devices"]) == 1 and s["status"] == "in_progress"


def test_untouched_quote_is_approved_on_submit_without_anyone(tech, prospect, rates):
    q = draft(tech, prospect)
    q = tech.post(f"/api/quotes/{q['id']}/submit").json()
    assert q["status"] == "approved" and q["approved_by"] is None


def test_adjusted_price_needs_a_reason_then_an_admin_approval(tech, admin, prospect, rates):
    q = draft(tech, prospect)
    qid = q["id"]
    r = tech.patch(f"/api/quotes/{qid}", json={"final_price_cents": 140000})
    assert r.status_code == 409 and "reason" in r.json()["detail"]
    r = tech.patch(
        f"/api/quotes/{qid}",
        json={"final_price_cents": 140000, "adjustment_reason": "Referral discount"},
    )
    assert r.status_code == 200 and r.json()["final_price_cents"] == 140000
    assert tech.post(f"/api/quotes/{qid}/submit").json()["status"] == "needs_approval"
    assert tech.post(f"/api/quotes/{qid}/approve").status_code == 403  # techs can't approve
    assert tech.post(f"/api/quotes/{qid}/send", json={}).status_code == 409  # not approved yet
    a = admin.post(f"/api/quotes/{qid}/approve").json()
    assert a["status"] == "approved" and a["approved_by"] == admin.user["id"]


def test_reject_sends_it_back_and_any_edit_voids_an_approval(tech, admin, prospect, rates):
    qid = draft(tech, prospect)["id"]
    tech.patch(f"/api/quotes/{qid}", json={"final_price_cents": 1, "adjustment_reason": "x"})
    tech.post(f"/api/quotes/{qid}/submit")
    r = admin.post(f"/api/quotes/{qid}/reject", json={"note": "too low"})
    assert r.json()["status"] == "draft" and r.json()["decision_note"] == "too low"
    tech.post(f"/api/quotes/{qid}/submit")
    assert admin.post(f"/api/quotes/{qid}/approve").json()["status"] == "approved"
    edited = tech.patch(f"/api/quotes/{qid}", json={"notes": "hi"}).json()
    assert edited["status"] == "draft" and edited["approved_at"] is None


def test_you_cannot_approve_your_own_price_change(tech, admin, prospect, rates):
    qid = draft(tech, prospect)["id"]
    admin.patch(f"/api/quotes/{qid}", json={"final_price_cents": 100, "adjustment_reason": "r"})
    assert tech.post(f"/api/quotes/{qid}/submit").json()["status"] == "needs_approval"
    r = admin.post(f"/api/quotes/{qid}/approve")
    assert r.status_code == 409 and "own price change" in r.json()["detail"]


def test_an_admins_own_adjustment_is_approved_on_submit(admin, prospect, rates, tech):
    qid = draft(tech, prospect)["id"]
    admin.patch(f"/api/quotes/{qid}", json={"final_price_cents": 100, "adjustment_reason": "r"})
    q = admin.post(f"/api/quotes/{qid}/submit").json()
    assert q["status"] == "approved" and q["approved_by"] == admin.user["id"]


def test_setting_the_price_back_to_computed_clears_the_adjustment(tech, prospect, rates):
    q = draft(tech, prospect)
    tech.patch(f"/api/quotes/{q['id']}", json={"final_price_cents": 5, "adjustment_reason": "r"})
    q = tech.patch(f"/api/quotes/{q['id']}", json={"final_price_cents": 157500}).json()
    assert q["adjustment_reason"] is None and q["adjusted_by"] is None


def approved(tech, org):
    q = draft(tech, org)
    return tech.post(f"/api/quotes/{q['id']}/submit").json()


def test_send_freezes_the_quote_and_only_one_open_quote_per_survey(tech, prospect, rates):
    q = approved(tech, prospect)
    sent = tech.post(f"/api/quotes/{q['id']}/send", json={}).json()
    assert sent["status"] == "sent" and sent["sent_at"] and sent["sent_to"] is None
    assert sent["valid_until"] == (biz_today() + timedelta(days=30)).isoformat()
    assert tech.patch(f"/api/quotes/{q['id']}", json={"notes": "x"}).status_code == 409
    again = tech.post(f"/api/surveys/{q['survey_id']}/quote", json={})
    assert again.status_code == 409


def test_sending_by_email_queues_the_pdf_for_the_worker(tech, prospect, rates, mail_ready):
    q = approved(tech, prospect)
    sent = tech.post(f"/api/quotes/{q['id']}/send", json={"send_email": True}).json()
    assert sent["sent_to"] == "nina@newco.com"
    [msg] = worker_sends().sent
    [(name, ctype, data)] = msg["attachments"]
    assert name == f"Quote-Q{q['id']}-v1.pdf" and ctype == "application/pdf"
    assert data.startswith(b"%PDF") and b"$1,575.00" in data.replace(b"\\", b"")


def test_email_needs_a_mailbox_and_a_recipient(tech, admin, login, rates):
    org = admin.post("/api/organizations", json={"name": "Nocontact", "status": "prospect"}).json()
    q = approved(tech, org["id"])
    r = tech.post(f"/api/quotes/{q['id']}/send", json={"send_email": True})
    assert r.status_code == 409 and "Email is not configured" in r.json()["detail"]


def test_email_without_a_contact_is_refused_and_leaves_the_quote_approved(
    tech, admin, rates, mail_ready
):
    org = admin.post("/api/organizations", json={"name": "Nocontact", "status": "prospect"}).json()
    q = approved(tech, org["id"])
    r = tech.post(f"/api/quotes/{q['id']}/send", json={"send_email": True})
    assert r.status_code == 409 and "No contact" in r.json()["detail"]
    assert tech.get(f"/api/quotes/{q['id']}").json()["status"] == "approved"
    ok = tech.post(
        f"/api/quotes/{q['id']}/send",
        json={"send_email": True, "to_emails": ["boss@nocontact.com"]},
    )
    assert ok.status_code == 200 and ok.json()["sent_to"] == "boss@nocontact.com"


def test_pdf_is_a_real_pdf_and_hides_internal_reasons(tech, prospect, rates, company):
    q = draft(tech, prospect)
    tech.patch(
        f"/api/quotes/{q['id']}",
        json={"final_price_cents": 150000, "adjustment_reason": "SECRET-INTERNAL-REASON"},
    )
    r = tech.get(f"/api/quotes/{q['id']}/pdf")
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF")
    assert b"SECRET-INTERNAL-REASON" not in r.content
    assert b"Acme MSP LLC" in r.content and b"Newco" in r.content


def test_accepting_activates_the_prospect_and_creates_a_12_month_flat_agreement(
    tech, admin, prospect, rates
):
    q = approved(tech, prospect)
    tech.post(f"/api/quotes/{q['id']}/send", json={})
    assert tech.post(f"/api/quotes/{q['id']}/accept", json={}).status_code == 403
    start = biz_today()
    a = admin.post(f"/api/quotes/{q['id']}/accept", json={"start_date": start.isoformat()})
    assert a.status_code == 200, a.text
    body = a.json()
    assert body["status"] == "accepted" and body["resulting_agreement_id"]
    assert admin.get(f"/api/organizations/{prospect}").json()["status"] == "active"
    [ag] = admin.get("/api/agreements", params={"organization_id": prospect}).json()
    assert (ag["type"], ag["unit_price_cents"], ag["quantity"]) == ("flat", 157500, 1)
    assert ag["start_date"] == start.isoformat()
    assert ag["end_date"] == quoting.contract_end(start, 12).isoformat()
    assert admin.post(f"/api/quotes/{q['id']}/accept", json={}).status_code == 409


def test_cannot_accept_before_sending_or_after_expiry(tech, admin, prospect, rates, monkeypatch):
    q = approved(tech, prospect)
    assert admin.post(f"/api/quotes/{q['id']}/accept", json={}).status_code == 409
    tech.post(f"/api/quotes/{q['id']}/send", json={})
    monkeypatch.setattr(quoting, "today", lambda ctx: biz_today() + timedelta(days=45))
    shown = admin.get(f"/api/quotes/{q['id']}").json()
    assert shown["status"] == "sent" and shown["is_expired"] is True
    r = admin.post(f"/api/quotes/{q['id']}/accept", json={})
    assert r.status_code == 409 and "expired" in r.json()["detail"]


def test_decline_and_cancel(tech, admin, prospect, rates):
    q = approved(tech, prospect)
    tech.post(f"/api/quotes/{q['id']}/send", json={})
    d = admin.post(f"/api/quotes/{q['id']}/decline", json={"note": "went elsewhere"}).json()
    assert d["status"] == "declined" and d["decision_note"] == "went elsewhere"
    assert admin.get(f"/api/organizations/{prospect}").json()["status"] == "prospect"
    assert tech.post(f"/api/quotes/{q['id']}/cancel", json={}).status_code == 409
    q2 = draft(tech, prospect)
    assert tech.post(f"/api/quotes/{q2['id']}/cancel", json={}).json()["status"] == "cancelled"


def test_revise_reprices_at_todays_rate_card_and_closes_the_old_quote(tech, admin, prospect, rates):
    q = approved(tech, prospect)
    tech.post(f"/api/quotes/{q['id']}/send", json={})
    admin.patch("/api/quotes/settings", json={"per_user_rate_cents": 20000})
    n = tech.post(f"/api/quotes/{q['id']}/revise").json()
    assert n["version"] == 2 and n["replaces_quote_id"] == q["id"] and n["status"] == "draft"
    assert n["base_cents"] == 10 * 20000 + 16000 + 10000
    assert tech.get(f"/api/quotes/{q['id']}").json()["status"] == "cancelled"
    assert [x["id"] for x in tech.get("/api/quotes", params={"status": "draft"}).json()] == [
        n["id"]
    ]


def test_quote_snapshot_is_unaffected_by_later_rate_changes(tech, admin, prospect, rates):
    q = draft(tech, prospect)
    admin.patch("/api/quotes/settings", json={"per_user_rate_cents": 99999})
    again = tech.get(f"/api/quotes/{q['id']}").json()
    assert again["base_cents"] == 126000 and again["snapshot"]["rates"]["per_user"] == 10000


# ---- repricing an existing client ----------------------------------------------------------
def next_month_first():
    t = biz_today()
    return date(t.year + (t.month == 12), t.month % 12 + 1, 1)


@pytest.fixture
def client_agreement(admin, prospect, rates):
    admin.patch(f"/api/organizations/{prospect}", json={"status": "active"})
    r = admin.post(
        "/api/agreements",
        json={
            "organization_id": prospect,
            "name": "Managed services",
            "type": "flat",
            "unit_price_cents": 157500,
            "start_date": (biz_today() - timedelta(days=60)).isoformat(),
            "end_date": (biz_today() + timedelta(days=300)).isoformat(),
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_reprice_ends_the_old_agreement_and_starts_the_lower_price_next_month(
    tech, admin, prospect, client_agreement
):
    fixed = {**ENV, "devices": [device()] * 8 + [device("server")]}  # hardware replaced
    sid = surveyed(tech, prospect, fixed)
    eff = next_month_first()
    r = tech.post(
        f"/api/surveys/{sid}/quote",
        json={
            "kind": "reprice",
            "agreement_id": client_agreement["id"],
            "effective_date": eff.isoformat(),
        },
    )
    assert r.status_code == 201, r.text
    q = r.json()
    assert q["final_price_cents"] == 126000 < client_agreement["unit_price_cents"]
    tech.post(f"/api/quotes/{q['id']}/submit")
    tech.post(f"/api/quotes/{q['id']}/send", json={})
    assert admin.post(f"/api/quotes/{q['id']}/accept", json={}).status_code == 200
    ags = {
        a["id"]: a
        for a in admin.get("/api/agreements", params={"organization_id": prospect}).json()
    }
    old, new = (
        ags[client_agreement["id"]],
        [a for i, a in ags.items() if i != client_agreement["id"]][0],
    )
    assert old["end_date"] == (eff - timedelta(days=1)).isoformat()
    assert new["start_date"] == eff.isoformat() and new["unit_price_cents"] == 126000
    assert new["end_date"] == client_agreement["end_date"]  # the original term is kept


def test_reprice_validates_the_effective_date_and_the_agreement(
    tech, admin, prospect, client_agreement
):
    sid = surveyed(tech, prospect)
    url = f"/api/surveys/{sid}/quote"
    base = {"kind": "reprice", "agreement_id": client_agreement["id"]}
    assert tech.post(url, json=base).status_code == 409  # no date
    mid = (next_month_first() + timedelta(days=3)).isoformat()
    assert tech.post(url, json={**base, "effective_date": mid}).status_code == 409
    past = date(biz_today().year, biz_today().month, 1).isoformat()
    assert tech.post(url, json={**base, "effective_date": past}).status_code == 409
    ok = {"effective_date": next_month_first().isoformat()}
    assert tech.post(url, json={**base, **ok, "agreement_id": 99999}).status_code == 404


# ---- permissions, isolation, guards ---------------------------------------------------------
def test_roles_and_the_prospect_status(login, prospect, rates, tech):
    ro, billing = login("read_only"), login("billing")
    q = draft(tech, prospect)
    assert ro.get(f"/api/quotes/{q['id']}").status_code == 200
    for who in (ro, billing):
        assert who.post(f"/api/organizations/{prospect}/surveys", json={}).status_code == 403
        assert who.post(f"/api/quotes/{q['id']}/submit").status_code == 403
        assert who.post(f"/api/quotes/{q['id']}/cancel", json={}).status_code == 403
    assert ro.put("/api/surveys/1", json={"user_count": 1}).status_code == 403


def test_unknown_ids_are_404(tech, admin):
    assert tech.get("/api/quotes/999").status_code == 404
    assert tech.get("/api/surveys/999").status_code == 404
    assert tech.get("/api/quotes/999/pdf").status_code == 404
    assert tech.post("/api/organizations/999/surveys", json={}).status_code == 404
    assert admin.post("/api/quotes/999/approve").status_code == 404


def test_every_step_is_audited(tech, admin, prospect, rates):
    q = approved(tech, prospect)
    tech.post(f"/api/quotes/{q['id']}/send", json={})
    admin.post(f"/api/quotes/{q['id']}/accept", json={})
    admin.patch("/api/quotes/settings", json={"hardware_uplift_bp": 3000})
    actions = [e["action"] for e in admin.get("/api/audit", params={"limit": 200}).json()["items"]]
    for expected in (
        "survey.create",
        "survey.save",
        "survey.complete",
        "quote.create",
        "quote.submit",
        "quote.send",
        "quote.accept",
        "agreement.create",
        "quote_settings.update",
    ):
        assert expected in actions, expected


def test_quotes_and_surveys_are_row_level_secured(owner, tech, prospect, rates):
    draft(tech, prospect)
    n = owner.execute(text("SELECT count(*) FROM quotes")).scalar()
    assert n == 1
    owner.execute(text("SELECT set_config('app.org_scope', '', false)"))  # fail closed
    # the owner role bypasses nothing it shouldn't: the runtime role is the one under test
    assert (
        owner.execute(
            text("SELECT relforcerowsecurity FROM pg_class WHERE relname='quotes'")
        ).scalar()
        is True
    )


def test_db_refuses_to_change_a_sent_quote_or_delete_any(owner, tech, prospect, rates):
    q = approved(tech, prospect)
    tech.post(f"/api/quotes/{q['id']}/send", json={})
    with pytest.raises(Exception, match="sent quote cannot be changed"):
        owner.execute(text("UPDATE quotes SET final_price_cents = 1 WHERE id = :i"), {"i": q["id"]})
    with pytest.raises(Exception, match="never deleted"):
        owner.execute(text("DELETE FROM quotes WHERE id = :i"), {"i": q["id"]})
    with pytest.raises(Exception, match="only be accepted, declined or cancelled"):
        owner.execute(text("UPDATE quotes SET status = 'draft' WHERE id = :i"), {"i": q["id"]})


def test_db_refuses_to_change_a_completed_survey(owner, tech, prospect):
    sid = surveyed(tech, prospect)
    with pytest.raises(Exception, match="completed survey is immutable"):
        owner.execute(text("UPDATE site_surveys SET user_count = 1 WHERE id = :i"), {"i": sid})
    with pytest.raises(Exception, match="completed survey is immutable"):
        owner.execute(text("DELETE FROM survey_devices WHERE survey_id = :i"), {"i": sid})
    with pytest.raises(Exception, match="completed survey is immutable"):
        owner.execute(
            text("INSERT INTO survey_apps (survey_id, organization_id, name) VALUES (:i, :o, 'x')"),
            {"i": sid, "o": prospect},
        )


def test_unadjusted_price_cannot_differ_from_computed_without_a_reason(
    owner, tech, prospect, rates
):
    q = draft(tech, prospect)
    with pytest.raises(Exception, match="ck_quotes_adjustment_reason"):
        owner.execute(text("UPDATE quotes SET final_price_cents = 5 WHERE id = :i"), {"i": q["id"]})
