"""Phase 14 portal polish: attachments, contact self-service and CSV export."""

import base64

import pytest

from app.config import get_settings
from tests.test_assets_api import portal_setup, synced  # noqa: F401
from tests.test_payments import final_invoice
from tests.test_portal import (  # noqa: F401
    add_contact,
    link_emails,
    portal_on,
    sign_in,
    two_clients,
)
from tests.vendorfakes import vendors  # noqa: F401

API = "/api/v1/portal"


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


@pytest.fixture(autouse=True)
def files_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "attachments_dir", str(tmp_path))
    return tmp_path


def mk_ticket(admin, org, contact, subject="Printer"):
    r = admin.post(
        "/api/v1/tickets", json={"organization_id": org, "contact_id": contact, "subject": subject}
    )
    assert r.status_code == 201, r.text
    return r.json()


def upload(client, ticket_id, name="notes.txt", data=b"hello"):
    return client.post(
        f"{API}/tickets/{ticket_id}/attachments",
        json={"filename": name, "content_base64": b64(data)},
    )


def actions(admin, action):
    return admin.get("/api/v1/audit", params={"action": action}).json()["items"]


@pytest.fixture
def world(admin, sign_in, two_clients):
    a, b = two_clients
    pat = add_contact(admin, a, "Pat", "pat@acme.com")
    bea = add_contact(admin, b, "Bea", "bea@beta.com")
    return dict(a=a, b=b, pat=pat, bea=bea, ticket=mk_ticket(admin, a, pat["id"]))


# ---- attachments ----
def test_upload_list_download_round_trip(admin, sign_in, world, files_dir):
    p = sign_in("pat@acme.com")
    r = upload(p, world["ticket"]["id"], data=b"hello world")
    assert r.status_code == 201, r.text
    body = r.json()
    assert set(body) == {"id", "filename", "size_bytes", "created_at"}
    assert body["filename"] == "notes.txt" and body["size_bytes"] == 11
    assert len([f for f in files_dir.rglob("*") if f.is_file()]) == 1
    listed = p.get(f"{API}/tickets/{world['ticket']['id']}/attachments").json()
    assert [x["id"] for x in listed] == [body["id"]]
    d = p.get(f"{API}/attachments/{body['id']}/download")
    assert d.status_code == 200 and d.content == b"hello world"
    assert d.headers["content-type"] == "application/octet-stream"
    assert d.headers["x-content-type-options"] == "nosniff"
    assert "attachment" in d.headers["content-disposition"]
    row = actions(admin, "portal.attachment_upload")[0]
    assert row["detail"]["contact_id"] == world["pat"]["id"] and row["detail"]["size"] == 11


def test_upload_is_visible_to_staff_with_source_and_uploader(admin, sign_in, world):
    p = sign_in("pat@acme.com")
    upload(p, world["ticket"]["id"])
    rows = admin.get(f"/api/v1/tickets/{world['ticket']['id']}/attachments").json()
    assert (rows[0]["source"], rows[0]["uploaded_by_name"]) == ("portal", "Pat")
    d = admin.get(f"/api/v1/attachments/{rows[0]['id']}/download")
    assert d.status_code == 200 and d.content == b"hello"


def test_upload_validation(admin, sign_in, world, monkeypatch):
    p = sign_in("pat@acme.com")
    tid = world["ticket"]["id"]
    monkeypatch.setattr(get_settings(), "max_attachment_bytes", 100)
    assert upload(p, tid, data=b"x" * 101).status_code == 413
    assert upload(p, tid, data=b"x" * 100).status_code == 201
    huge = p.post(
        f"{API}/tickets/{tid}/attachments",
        json={"filename": "a.txt", "content_base64": "A" * 5000},
    )
    assert huge.status_code == 413
    assert upload(p, tid, name="run.exe").status_code == 415
    assert upload(p, tid, name="noext").status_code == 415
    bad = p.post(
        f"{API}/tickets/{tid}/attachments",
        json={"filename": "a.txt", "content_base64": "!!not base64!!"},
    )
    assert bad.status_code == 422
    assert upload(p, tid, data=b"").status_code == 422


def test_oversized_body_is_rejected_before_parsing(admin, sign_in, world, monkeypatch):
    p = sign_in("pat@acme.com")
    url = f"{API}/tickets/{world['ticket']['id']}/attachments"
    monkeypatch.setattr(get_settings(), "max_attachment_bytes", 100)
    big = b'{"filename": "a.txt", "content_base64": "' + b"A" * 5000 + b'"}'
    hdr = {"content-type": "application/json"}
    # declared Content-Length over the cap
    assert p.post(url, content=big, headers=hdr).status_code == 413

    # chunked body (no Content-Length) is counted as it streams
    def chunks():
        for i in range(0, len(big), 500):
            yield big[i : i + 500]

    assert p.post(url, content=chunks(), headers=hdr).status_code == 413
    assert upload(p, world["ticket"]["id"], data=b"x" * 100).status_code == 201


def test_raising_the_setting_raises_the_cap(admin, sign_in, world, monkeypatch):
    p = sign_in("pat@acme.com")
    monkeypatch.setattr(get_settings(), "max_attachment_bytes", 20 * 1024 * 1024)
    assert upload(p, world["ticket"]["id"], data=b"x" * (11 * 1024 * 1024)).status_code == 201


def test_closed_ticket_refuses_uploads(admin, sign_in, world):
    admin.patch(f"/api/v1/tickets/{world['ticket']['id']}", json={"status": "closed"})
    assert upload(sign_in("pat@acme.com"), world["ticket"]["id"]).status_code == 409


def test_hourly_upload_limit(admin, sign_in, world):
    p = sign_in("pat@acme.com")
    codes = [upload(p, world["ticket"]["id"], data=b"x").status_code for _ in range(21)]
    assert codes[:20] == [201] * 20 and codes[20] == 429


def test_rate_limit_is_checked_before_decoding(admin, sign_in, world, monkeypatch):
    from app import portal_files

    p = sign_in("pat@acme.com")
    for _ in range(20):
        assert upload(p, world["ticket"]["id"], data=b"x").status_code == 201

    def must_not_decode(*args, **kwargs):
        raise AssertionError("decoded before the rate limit was checked")

    monkeypatch.setattr(portal_files, "_decode", must_not_decode)
    assert upload(p, world["ticket"]["id"], data=b"x" * 50).status_code == 429


def test_org_storage_quota(admin, sign_in, world, monkeypatch):
    from app import portal_files

    monkeypatch.setattr(get_settings(), "portal_org_storage_bytes", 10)
    p = sign_in("pat@acme.com")
    assert upload(p, world["ticket"]["id"], data=b"x" * 8).status_code == 201
    calls = []
    real = portal_files._decode
    monkeypatch.setattr(portal_files, "_decode", lambda *a: calls.append(1) or real(*a))
    r = upload(p, world["ticket"]["id"], data=b"x" * 8)
    assert r.status_code == 413
    assert r.json()["detail"] == "This client's file storage is full. Contact us."
    assert calls == []  # refused from the encoded length, without decoding
    # the quota is per client: another organization still has room
    bea_ticket = mk_ticket(admin, world["b"], world["bea"]["id"])
    assert upload(sign_in("bea@beta.com"), bea_ticket["id"], data=b"x" * 8).status_code == 201


def test_filename_is_sanitised(admin, sign_in, world, files_dir):
    p = sign_in("pat@acme.com")
    r = upload(p, world["ticket"]["id"], name="../../etc/passwd.txt")
    assert r.status_code == 201 and r.json()["filename"] == "passwd.txt"
    r = upload(p, world["ticket"]["id"], name="..\\..\\secret.txt")
    assert r.json()["filename"] == "secret.txt"
    assert all(files_dir in f.parents for f in files_dir.rglob("*"))
    assert upload(p, world["ticket"]["id"], name="../../etc/passwd").status_code == 415


def test_attachments_are_isolated(admin, sign_in, world, two_clients):
    a = world["a"]
    boss = add_contact(admin, a, "Boss", "boss@acme.com", all_tickets=True)
    colleague = add_contact(admin, a, "Col", "col@acme.com")
    tid = world["ticket"]["id"]
    att = upload(sign_in("pat@acme.com"), tid).json()

    bea = sign_in("bea@beta.com")
    assert upload(bea, tid).status_code == 404
    assert bea.get(f"{API}/tickets/{tid}/attachments").status_code == 404
    assert bea.get(f"{API}/attachments/{att['id']}/download").status_code == 404

    col = sign_in("col@acme.com")  # same client, but without whole-client ticket visibility
    assert upload(col, tid).status_code == 404
    assert col.get(f"{API}/tickets/{tid}/attachments").status_code == 404
    assert col.get(f"{API}/attachments/{att['id']}/download").status_code == 404
    assert colleague["id"] != boss["id"]

    boss_c = sign_in("boss@acme.com")
    assert boss_c.get(f"{API}/attachments/{att['id']}/download").status_code == 200


def test_email_attachments_stay_internal(admin, sign_in, world, owner, files_dir):
    from sqlalchemy import text

    tid = world["ticket"]["id"]
    em = owner.execute(
        text(
            "INSERT INTO email_messages (direction, organization_id, subject, send_status) "
            "VALUES ('in', :o, 's', 'sent') RETURNING id"
        ),
        {"o": world["a"]},
    ).scalar()
    (files_dir / str(tid)).mkdir()
    (files_dir / str(tid) / "k").write_bytes(b"secret")
    att = owner.execute(
        text(
            "INSERT INTO attachments (email_message_id, ticket_id, organization_id, filename, "
            "size_bytes, sha256, storage_key) VALUES (:e, :t, :o, 'mail.txt', 6, 'x', :k) "
            "RETURNING id"
        ),
        {"e": em, "t": tid, "o": world["a"], "k": f"{tid}/k"},
    ).scalar()
    p = sign_in("pat@acme.com")
    assert p.get(f"{API}/tickets/{tid}/attachments").json() == []
    assert p.get(f"{API}/attachments/{att}/download").status_code == 404
    assert admin.get(f"/api/v1/attachments/{att}/download").status_code == 200


# ---- contact self-service ----
def test_contact_edits_their_details(admin, sign_in, world):
    p = sign_in("pat@acme.com")
    r = p.patch(
        f"{API}/me/contact", json={"name": "  Patricia ", "phone": "555-0100", "title": "CFO"}
    )
    assert r.status_code == 200 and r.json()["contact_name"] == "Patricia"
    assert r.json()["email"] == "pat@acme.com"
    staff = admin.get(f"/api/v1/organizations/{world['a']}/contacts").json()
    pat = next(c for c in staff if c["id"] == world["pat"]["id"])
    assert (pat["name"], pat["phone"], pat["title"]) == ("Patricia", "555-0100", "CFO")
    row = actions(admin, "portal.contact_update")[0]
    assert row["detail"]["organization_id"] == world["a"]
    assert row["before"]["name"] == "Pat" and row["after"]["name"] == "Patricia"
    r = p.patch(f"{API}/me/contact", json={"name": "Patricia", "phone": None, "title": None})
    assert r.status_code == 200


def test_contact_patch_rejects_email_and_bad_values(admin, sign_in, world):
    p = sign_in("pat@acme.com")
    for body in (
        {"name": "Pat", "email": "evil@x.com"},
        {"name": "Pat", "portal_access": True},
        {"name": "   "},
        {"name": "x" * 201},
        {"name": "Pat", "phone": "1" * 51},
        {"name": "Pat", "title": "t" * 101},
    ):
        assert p.patch(f"{API}/me/contact", json=body).status_code == 422, body
    assert p.get(f"{API}/me").json()["email"] == "pat@acme.com"


def test_me_returns_phone_and_title_and_name_only_patch_keeps_them(admin, sign_in, world):
    p = sign_in("pat@acme.com")
    r = p.patch(f"{API}/me/contact", json={"name": "Pat", "phone": "555-0100", "title": "CFO"})
    assert r.status_code == 200
    me = p.get(f"{API}/me").json()
    assert (me["phone"], me["title"]) == ("555-0100", "CFO")
    # the My details page sends back what /me returned, so a name-only change keeps them
    r = p.patch(
        f"{API}/me/contact", json={"name": "Patricia", "phone": me["phone"], "title": me["title"]}
    )
    assert r.status_code == 200
    me = p.get(f"{API}/me").json()
    assert (me["contact_name"], me["phone"], me["title"]) == ("Patricia", "555-0100", "CFO")


# ---- exports ----
def test_ticket_export_is_own_org_only_and_neutralises_formulas(admin, sign_in, world):
    mk_ticket(admin, world["a"], world["pat"]["id"], subject="=HYPERLINK(1)")
    mk_ticket(admin, world["b"], world["bea"]["id"], subject="Beta secret")
    r = sign_in("pat@acme.com").get(f"{API}/export/tickets.csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert r.headers["content-disposition"].startswith('attachment; filename="tickets-')
    lines = r.text.strip().split("\r\n")
    assert lines[0] == "number,subject,status,priority,created_at,closed_at"
    assert len(lines) == 3 and "Beta secret" not in r.text
    assert "'=HYPERLINK(1)" in r.text and "\r\n=HYPERLINK" not in r.text
    assert actions(admin, "portal.export")[0]["detail"] == {
        "kind": "tickets",
        "rows": 2,
        "contact_id": world["pat"]["id"],
    }


def test_ticket_export_respects_contact_visibility(admin, sign_in, world):
    boss = add_contact(admin, world["a"], "Boss", "boss@acme.com", all_tickets=True)
    mk_ticket(admin, world["a"], boss["id"], subject="Boss only")
    assert "Boss only" not in sign_in("pat@acme.com").get(f"{API}/export/tickets.csv").text
    assert "Boss only" in sign_in("boss@acme.com").get(f"{API}/export/tickets.csv").text


def test_invoice_export_is_for_billing_contacts(admin, biller, sign_in, world):
    add_contact(admin, world["a"], "Fin", "fin@acme.com", billing=True)
    final_invoice(biller, world["a"], cents=12345)
    final_invoice(biller, world["b"], cents=99900)
    assert sign_in("pat@acme.com").get(f"{API}/export/invoices.csv").status_code == 403
    r = sign_in("fin@acme.com").get(f"{API}/export/invoices.csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    lines = r.text.strip().split("\r\n")
    assert lines[0] == "number,issue_date,due_date,status,total,balance"
    assert len(lines) == 2 and ",123.45,123.45" in lines[1] and "999.00" not in r.text
    assert actions(admin, "portal.export")[0]["detail"]["kind"] == "invoices"


def test_device_export_needs_sharing(admin, synced, sign_in):  # noqa: F811
    org, contact = portal_setup(admin, synced, published=False, flag=True)
    assert sign_in("pat@acme.com").get(f"{API}/export/devices.csv").status_code == 403
    admin.put(f"/api/v1/organizations/{org['id']}/assets-sharing", json={"published": True})
    r = sign_in("pat@acme.com").get(f"{API}/export/devices.csv")
    assert r.status_code == 200
    lines = r.text.strip().split("\r\n")
    assert lines[0] == "name,kind,manufacturer,model,warranty_end,warranty_status"
    assert len(lines) == 5 and "PC-OLD" in r.text
    assert actions(admin, "portal.export")[0]["detail"]["rows"] == 4


def test_new_endpoints_need_a_portal_session(anon):
    for method, path in (
        ("GET", f"{API}/tickets/1/attachments"),
        ("POST", f"{API}/tickets/1/attachments"),
        ("GET", f"{API}/attachments/1/download"),
        ("PATCH", f"{API}/me/contact"),
        ("GET", f"{API}/export/tickets.csv"),
        ("GET", f"{API}/export/invoices.csv"),
        ("GET", f"{API}/export/devices.csv"),
    ):
        r = anon.request(method, path, json={} if method in ("POST", "PATCH") else None)
        assert r.status_code == 401, path
