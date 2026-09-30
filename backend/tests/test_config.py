import pytest


@pytest.mark.parametrize(
    "path,body,patch",
    [
        ("queues", {"name": "Projects"}, {"name": "Projects 2"}),
        ("categories", {"name": "Printers"}, {"name": "Printing"}),
        ("work-types", {"name": "Travel"}, {"name": "Travel time"}),
        (
            "priorities",
            {
                "name": "Emergency",
                "rank": 0 + 1,
                "first_response_minutes": 15,
                "resolution_minutes": 120,
            },
            {"rank": 2, "resolution_minutes": 90},
        ),
    ],
)
def test_lookup_crud_archive_and_audit(admin, path, body, patch):
    r = admin.post(f"/api/{path}", json=body)
    assert r.status_code == 201, r.text
    item = r.json()
    assert admin.post(f"/api/{path}", json=body).status_code == 409  # duplicate active name
    r = admin.patch(f"/api/{path}/{item['id']}", json=patch)
    assert r.status_code == 200
    for key, value in patch.items():
        assert r.json()[key] == value
    assert admin.post(f"/api/{path}/{item['id']}/archive").json()["archived_at"]
    assert item["id"] not in [x["id"] for x in admin.get(f"/api/{path}").json()]
    assert item["id"] in [
        x["id"] for x in admin.get(f"/api/{path}", params={"include_archived": True}).json()
    ]
    assert admin.post(f"/api/{path}", json=body).status_code == 201  # name reusable once archived
    # unarchiving conflicts only if its (current) name is now taken by another active item
    unarchived = admin.post(f"/api/{path}/{item['id']}/unarchive")
    assert unarchived.status_code == (200 if "name" in patch else 409)
    assert admin.patch(f"/api/{path}/999", json={"name": "x"}).status_code == 404
    assert admin.post(f"/api/{path}/999/archive").status_code == 404
    assert admin.post(f"/api/{path}/999/unarchive").status_code == 404
    label = {
        "work-types": "work_type",
        "categories": "category",
        "queues": "queue",
        "priorities": "priority",
    }[path]
    actions = {
        a["action"] for a in admin.get("/api/audit", params={"action": f"{label}."}).json()["items"]
    }
    assert {f"{label}.create", f"{label}.update", f"{label}.archive"} <= actions


def test_default_queue_is_swappable_and_protected(admin):
    queues = {q["name"]: q for q in admin.get("/api/queues").json()}
    assert queues["Support"]["is_default"] and not queues["Security"]["is_default"]
    assert admin.post(f"/api/queues/{queues['Support']['id']}/archive").status_code == 409
    assert (
        admin.patch(
            f"/api/queues/{queues['Support']['id']}", json={"is_default": False}
        ).status_code
        == 409
    )
    admin.patch(f"/api/queues/{queues['Security']['id']}", json={"is_default": True})
    now = {q["name"]: q["is_default"] for q in admin.get("/api/queues").json()}
    assert now == {"Support": False, "Security": True}
    assert admin.post(f"/api/queues/{queues['Support']['id']}/archive").status_code == 200
    made = admin.post("/api/queues", json={"name": "Third", "is_default": True}).json()
    assert made["is_default"]
    assert sum(q["is_default"] for q in admin.get("/api/queues").json()) == 1


def test_new_tickets_use_the_current_default_queue_and_priority(admin, org_ctx):
    sec = next(q for q in admin.get("/api/queues").json() if q["name"] == "Security")
    high = next(p for p in admin.get("/api/priorities").json() if p["name"] == "High")
    admin.patch(f"/api/queues/{sec['id']}", json={"is_default": True})
    admin.patch(f"/api/priorities/{high['id']}", json={"is_default": True})
    t = admin.post("/api/tickets", json={"organization_id": org_ctx["org"], "subject": "x"}).json()
    assert t["queue_name"] == "Security" and t["priority_name"] == "High"


def test_priorities_are_listed_by_rank(admin):
    names = [p["name"] for p in admin.get("/api/priorities").json()]
    assert names == ["Urgent", "High", "Normal", "Low"]


def test_settings_read_update_and_validation(admin, login):
    s = login("read_only").get("/api/settings").json()
    assert s["timezone"] == "America/Chicago" and s["business_days"] == [0, 1, 2, 3, 4]
    assert s["billing_increment_minutes"] == 15 and s["sla_at_risk_percent"] == 25
    r = admin.patch(
        "/api/settings",
        json={
            "timezone": "America/New_York",
            "business_days": [4, 0, 0, 1],
            "business_start_minute": 420,
            "business_end_minute": 1080,
            "sla_at_risk_percent": 10,
        },
    )
    assert r.status_code == 200
    assert r.json()["business_days"] == [0, 1, 4] and r.json()["timezone"] == "America/New_York"
    for bad in (
        {"timezone": "Mars/Base"},
        {"business_days": []},
        {"business_days": [9]},
        {"business_start_minute": 1100},
        {"business_end_minute": 2000},
    ):
        assert admin.patch("/api/settings", json=bad).status_code == 409, bad
    assert admin.patch("/api/settings", json={"billing_increment_minutes": 0}).status_code == 422
    # a rejected change leaves settings untouched
    assert admin.get("/api/settings").json()["timezone"] == "America/New_York"
    assert any(
        a["action"] == "settings.update"
        for a in admin.get("/api/audit", params={"action": "settings."}).json()["items"]
    )


def test_mail_status_reports_unconfigured_by_default(admin, owner):
    s = admin.get("/api/mail/status").json()
    assert s["configured"] is False and s["mailbox"] is None and s["worker_seen_at"] is None
    assert s["outbound_pending"] == 0
    assert s["tickets_needing_triage"] == 0 and s["messages_ingested"] == 0


def test_worker_reports_its_own_configuration_and_liveness(admin):
    from app.mail.ingest import heartbeat

    heartbeat("support@msp.com")
    s = admin.get("/api/mail/status").json()
    assert s["configured"] is True and s["mailbox"] == "support@msp.com" and s["worker_seen_at"]
    heartbeat(None)  # worker running, but mail not configured
    s = admin.get("/api/mail/status").json()
    assert s["configured"] is False and s["worker_seen_at"]
