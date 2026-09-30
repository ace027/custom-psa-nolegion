import hashlib
from pathlib import Path

import pytest
from sqlalchemy import text

from app.config import get_settings


@pytest.fixture
def unmatched(owner):
    """A ticket that arrived by email from an unknown sender, with a note, email and file."""

    def _make():
        tid = owner.execute(
            text(
                "INSERT INTO tickets (queue_id, priority_id, subject, description, source, "
                "requester_email, status) SELECT q.id, p.id, 'Help', 'body', 'email', "
                "'stranger@nowhere.com', 'new' FROM queues q, priorities p "
                "WHERE q.is_default AND p.is_default RETURNING id"
            )
        ).scalar_one()
        eid = owner.execute(
            text(
                "INSERT INTO email_messages (direction, ticket_id, from_email, subject, body_text, "
                "graph_message_id) VALUES ('in', :t, 'stranger@nowhere.com', 'Help', 'body', 'g1') "
                "RETURNING id"
            ),
            {"t": tid},
        ).scalar_one()
        owner.execute(
            text(
                "INSERT INTO ticket_notes (ticket_id, author_email, visibility, source, body, "
                "email_message_id) VALUES (:t, 'stranger@nowhere.com', 'customer', 'email', 'hi', :e)"
            ),
            {"t": tid, "e": eid},
        )
        owner.execute(
            text(
                "INSERT INTO attachments (email_message_id, ticket_id, filename, size_bytes, sha256, "
                "storage_key) VALUES (:e, :t, 'a.txt', 3, 'x', 'k')"
            ),
            {"e": eid, "t": tid},
        )
        return tid

    return _make


def test_unmatched_tickets_are_flagged_and_listed(admin, unmatched):
    tid = unmatched()
    t = admin.get(f"/api/tickets/{tid}").json()
    assert t["needs_triage"] and t["organization_name"] is None
    assert admin.get("/api/tickets", params={"needs_triage": True}).json()["total"] == 1
    assert admin.get("/api/dashboard").json()["counts"]["needs_triage"] == 1
    assert admin.get("/api/mail/status").json()["tickets_needing_triage"] == 1
    assert admin.get(f"/api/tickets/{tid}/notes").json()[0]["email_status"] == "received"


def test_triage_assigns_org_and_moves_children(admin, owner, unmatched, org_ctx):
    tid = unmatched()
    r = admin.patch(
        f"/api/tickets/{tid}",
        json={"organization_id": org_ctx["org"], "contact_id": org_ctx["contact"]},
    )
    assert r.status_code == 200 and not r.json()["needs_triage"]
    for table in ("ticket_notes", "attachments", "email_messages"):
        orgs = {
            row[0]
            for row in owner.execute(
                text(f"SELECT organization_id FROM {table} WHERE ticket_id = :t"), {"t": tid}
            )
        }
        assert orgs == {org_ctx["org"]}, table
    entry = admin.get("/api/audit", params={"action": "ticket.triage"}).json()["items"]
    assert entry and entry[0]["detail"] == {"triage": True}
    # once matched, the org is locked
    other = admin.post("/api/organizations", json={"name": "Elsewhere"}).json()
    assert (
        admin.patch(f"/api/tickets/{tid}", json={"organization_id": other["id"]}).status_code == 409
    )


def test_triage_rejects_unknown_org_and_foreign_contact(admin, unmatched, org_ctx, make_org):
    tid = unmatched()
    assert admin.patch(f"/api/tickets/{tid}", json={"organization_id": 999}).status_code == 404
    assert admin.patch(f"/api/tickets/{tid}", json={"organization_id": None}).status_code in (
        200,
        404,
        409,
    )
    other = make_org("Other")
    r = admin.patch(
        f"/api/tickets/{tid}",
        json={"organization_id": other["id"], "contact_id": org_ctx["contact"]},
    )
    assert r.status_code == 409


def test_time_cannot_be_logged_until_ticket_is_matched(admin, unmatched):
    tid = unmatched()
    wt = admin.get("/api/work-types").json()[0]["id"]
    assert (
        admin.post(f"/api/tickets/{tid}/time", json={"work_type_id": wt, "minutes": 5}).status_code
        == 409
    )


# ---- attachments ----
@pytest.fixture
def stored_file(tmp_path, monkeypatch, owner, unmatched, admin, org_ctx):
    monkeypatch.setattr(get_settings(), "attachments_dir", str(tmp_path))
    tid = unmatched()
    admin.patch(f"/api/tickets/{tid}", json={"organization_id": org_ctx["org"]})
    data = b"<script>alert(1)</script>"
    (tmp_path / "1").mkdir()
    (tmp_path / "1" / "abc").write_bytes(data)
    owner.execute(
        text(
            "UPDATE attachments SET filename = '../evil name<>.html', size_bytes = :s, "
            "sha256 = :h, storage_key = '1/abc' WHERE ticket_id = :t"
        ),
        {"s": len(data), "h": hashlib.sha256(data).hexdigest(), "t": tid},
    )
    return tid, data


def test_attachment_list_and_safe_download(admin, login, stored_file):
    tid, data = stored_file
    listed = admin.get(f"/api/tickets/{tid}/attachments").json()
    assert len(listed) == 1 and listed[0]["size_bytes"] == len(data)
    r = login("read_only").get(f"/api/attachments/{listed[0]['id']}/download")
    assert r.status_code == 200 and r.content == data
    assert r.headers["content-type"] == "application/octet-stream"
    assert r.headers["content-disposition"].startswith("attachment;")
    assert (
        ".." not in r.headers["content-disposition"] and "<" not in r.headers["content-disposition"]
    )
    assert r.headers["x-content-type-options"] == "nosniff"
    assert admin.get("/api/attachments/999/download").status_code == 404
    assert admin.get("/api/tickets/999/attachments").status_code == 404


def test_download_refuses_path_traversal_and_missing_files(admin, owner, stored_file, tmp_path):
    tid, _ = stored_file
    aid = admin.get(f"/api/tickets/{tid}/attachments").json()[0]["id"]
    (Path(tmp_path).parent / "secret.txt").write_text("nope")
    owner.execute(text("UPDATE attachments SET storage_key = '../secret.txt'"))
    assert admin.get(f"/api/attachments/{aid}/download").status_code == 404
    owner.execute(text("UPDATE attachments SET storage_key = '1/missing'"))
    assert admin.get(f"/api/attachments/{aid}/download").status_code == 404
