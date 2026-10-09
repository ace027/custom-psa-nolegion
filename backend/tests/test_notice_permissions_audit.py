import pytest

from tests.test_notices import notices, overdue, prepare, set_gap
from tests.test_statements import statement

ROLES = ["admin", "tech", "billing", "read_only"]
ALLOWED = {"read": set(ROLES), "write": {"admin", "billing"}, "finalize": {"admin", "billing"}}

CALLS = [
    ("GET", "/api/billing/reminder-stages", None, "read"),
    ("PATCH", "/api/billing/reminder-stages/1", {"subject": "Hello"}, "write"),
    ("POST", "/api/organizations/1/statements", None, "write"),
    ("GET", "/api/organizations/1/statements", None, "read"),
    ("GET", "/api/statements/1", None, "read"),
    ("GET", "/api/statements/1/pdf", None, "read"),
    ("POST", "/api/statements/1/email", {"send": False}, "write"),
    ("POST", "/api/statements/1/email", {"send": True}, "finalize"),
    ("GET", "/api/billing-notices", None, "read"),
    ("GET", "/api/billing-notices/1", None, "read"),
    ("PATCH", "/api/billing-notices/1", {"subject": "x"}, "write"),
    ("POST", "/api/billing-notices/1/refresh", None, "write"),
    ("POST", "/api/billing-notices/1/send", None, "finalize"),
    ("POST", "/api/billing-notices/1/dismiss", {"reason": "because"}, "finalize"),
    ("POST", "/api/billing-notices/send", {"ids": [1]}, "finalize"),
    ("POST", "/api/billing-notices/prepare-reminders", None, "write"),
    ("POST", "/api/billing-notices/prepare-statements", None, "write"),
    ("POST", "/api/organizations/1/reminders", {}, "write"),
    ("POST", "/api/invoices/1/email", None, "write"),
]


@pytest.mark.parametrize("role", ROLES)
def test_notice_role_matrix(role, login):
    client = login(role)
    for method, path, body, need in CALLS:
        r = client.request(method, path, json=body)
        if role in ALLOWED[need]:
            assert r.status_code not in (401, 403), (role, method, path, r.status_code, r.text)
        else:
            assert r.status_code == 403, (role, method, path, r.status_code)


def test_unauthenticated_notice_requests_get_401(anon):
    for method, path, body, _ in CALLS:
        assert anon.request(method, path, json=body).status_code == 401, (method, path)


def test_every_notice_write_is_audited(admin, biller, client_org, clock, mail_ready):
    def audited(action):
        return admin.get("/api/audit", params={"action": action}).json()["total"]

    stage = biller.get("/api/billing/reminder-stages").json()[0]
    assert (
        biller.patch(
            f"/api/billing/reminder-stages/{stage['id']}", json={"subject": "Hi"}
        ).status_code
        == 200
    )
    assert audited("reminder_stage.update") == 1

    overdue(biller, client_org)
    clock(2)
    prepare(biller)
    n = notices(biller, status="pending")[0]
    assert audited("notice.create") == 1

    assert (
        biller.patch(f"/api/billing-notices/{n['id']}", json={"subject": "Edited"}).status_code
        == 200
    )
    assert audited("notice.edit") == 1
    assert biller.post(f"/api/billing-notices/{n['id']}/refresh").status_code == 200
    assert audited("notice.refresh") == 1
    assert biller.post(f"/api/billing-notices/{n['id']}/send").status_code == 200
    assert audited("notice.send") == 1

    statement(biller, client_org)
    assert audited("statement.create") == 1

    clock(40)
    set_gap(admin, 0)  # the test clock moves business dates, not created_at
    prepare(biller)
    n2 = notices(biller, status="pending")[0]
    assert (
        biller.post(
            f"/api/billing-notices/{n2['id']}/dismiss", json={"reason": "called them"}
        ).status_code
        == 200
    )
    assert audited("notice.dismiss") == 1
