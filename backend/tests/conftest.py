"""Tests run against a REAL PostgreSQL (no SQLite): RLS and partial indexes must be exercised.

Requires the roles psa_owner / psa_app and a database `psa_test` owned by psa_owner
(see docs/DEVELOPMENT.md). Override the host/ports via the PSA_TEST_* variables.
"""

import os

HOST = os.environ.get("PSA_TEST_DB_HOST", "localhost")
PORT = os.environ.get("PSA_TEST_DB_PORT", "5432")
NAME = os.environ.get("PSA_TEST_DB_NAME", "psa_test")
os.environ["DATABASE_URL"] = f"postgresql+psycopg://psa_app:app_dev@{HOST}:{PORT}/{NAME}"
os.environ["MIGRATION_DATABASE_URL"] = (
    f"postgresql+psycopg://psa_owner:owner_dev@{HOST}:{PORT}/{NAME}"
)
os.environ["ENVIRONMENT"] = "development"
os.environ["DEV_LOGIN_ENABLED"] = "true"
os.environ["ENTRA_TENANT_ID"] = "tenant-1"
os.environ["ENTRA_CLIENT_ID"] = "client-1"
os.environ["ENTRA_CLIENT_SECRET"] = "secret-1"
os.environ["SESSION_SECRET"] = "test-secret"
os.environ["CREDENTIALS_KEY"] = (
    "ZmFrZS1rZXktZm9yLXRlc3RzLW9ubHktMDAwMDAwMDA="  # test key, not a secret
)

import pytest  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

from alembic import command  # noqa: E402
from app.main import app  # noqa: E402

TABLES = (
    "timesheets, timers, internal_time_entries, time_categories, csat_surveys, ticket_links, custom_fields, ticket_types, ticket_statuses, holidays, ticket_auto_acks, ticket_escalations, canned_responses, asset_overrides, asset_sources, assets, sync_runs, integration_client_maps, integrations, quotes, survey_apps, survey_devices, site_surveys, staff_notifications, outbound_attachments, billing_notice_invoices, billing_notices, statements, "
    "write_offs, payment_applications, payments, invoice_counters, product_charges, invoice_lines, invoices, billing_runs, "
    "agreement_quantity_log, agreements, products, org_work_type_rates, "
    "attachments, time_entries, ticket_notes, email_messages, tickets, audit_log, sessions, "
    "contacts, sites, organizations, users, queues, categories, priorities, work_types"
)

RESEED = """
INSERT INTO ticket_statuses (name, behavior, position) VALUES
  ('New','new',10), ('Open','open',20), ('Waiting on customer','waiting_on_customer',30),
  ('Resolved','resolved',40), ('Closed','closed',50);
INSERT INTO queues (name, is_default) VALUES ('Support', true), ('Security', false);
INSERT INTO categories (name) VALUES ('General'), ('Microsoft 365'), ('Network');
INSERT INTO priorities (name, rank, first_response_minutes, resolution_minutes, is_default)
  VALUES ('Urgent', 1, 30, 240, false), ('High', 2, 60, 480, false),
         ('Normal', 3, 240, 1440, true), ('Low', 4, 480, 4320, false);
INSERT INTO work_types (name) VALUES ('Remote'), ('Onsite'), ('After hours');
INSERT INTO time_categories (name) VALUES ('Administration'), ('Training'), ('Meeting'),
  ('Paid time off');
DELETE FROM settings; INSERT INTO settings (id) VALUES (1);
DELETE FROM mailbox_status; INSERT INTO mailbox_status (id) VALUES (1);
DELETE FROM quote_settings; INSERT INTO quote_settings (id) VALUES (1);
ALTER SEQUENCE ticket_number_seq RESTART WITH 10001;
UPDATE work_types SET rate_cents = NULL, taxable = false;
"""
HIT_ROUTES: set[tuple[str, str]] = set()
STAGE_DEFAULTS: list[dict] = []


class RouteRecorder:
    """ASGI wrapper that records which (method, route template) the suite exercised."""

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        await self.inner(scope, receive, send)
        if scope["type"] == "http" and scope.get("route") is not None:
            HIT_ROUTES.add((scope["method"], scope["route"].path))


@pytest.fixture(scope="session")
def owner_engine():
    engine = create_engine(os.environ["MIGRATION_DATABASE_URL"])
    with engine.begin() as c:
        c.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")
    with engine.connect() as c:  # remember the seeded reminder stages so tests can edit freely
        STAGE_DEFAULTS.extend(
            dict(r._mapping)
            for r in c.execute(
                text(
                    "SELECT id, position, name, days_past_due, subject, body, enabled "
                    "FROM reminder_stages ORDER BY id"
                )
            )
        )
    yield engine
    engine.dispose()


@pytest.fixture(autouse=True)
def clean_db(owner_engine):
    with owner_engine.begin() as c:
        c.execute(text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))
        for stmt in RESEED.strip().split(";\n"):
            if stmt.strip():
                c.execute(text(stmt))
        for row in STAGE_DEFAULTS:
            c.execute(
                text(
                    "UPDATE reminder_stages SET position=:position, name=:name, "
                    "days_past_due=:days_past_due, subject=:subject, body=:body, enabled=:enabled "
                    "WHERE id=:id"
                ),
                row,
            )


@pytest.fixture
def owner(owner_engine):
    """Autocommit owner connection for arranging/inspecting data. Autocommit matters: an open
    owner transaction would hold locks and deadlock against the API's own connections."""
    with owner_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as c:
        c.execute(text("SELECT set_config('app.org_scope', 'all', false)"))
        yield c


@pytest.fixture
def make_user(owner_engine):
    def _make(role: str = "admin", email: str | None = None, active: bool = True) -> dict:
        email = email or f"{role}@example.com"
        with owner_engine.begin() as c:
            row = c.execute(
                text(
                    "INSERT INTO users (email, display_name, role, is_active) "
                    "VALUES (:e, :n, :r, :a) "
                    "ON CONFLICT ((lower(email))) DO UPDATE SET role = EXCLUDED.role "
                    "RETURNING id"
                ),
                {"e": email, "n": f"{role} user", "r": role, "a": active},
            ).one()
        return {"id": row.id, "email": email, "role": role}

    return _make


@pytest.fixture
def login(make_user):
    def _login(role: str = "admin", email: str | None = None) -> TestClient:
        user = make_user(role, email)
        client = TestClient(RouteRecorder(app), headers={"X-Requested-With": "psa"})
        r = client.post("/api/auth/dev-login", json={"email": user["email"]})
        assert r.status_code == 200, r.text
        client.user = user
        return client

    return _login


@pytest.fixture
def admin(login):
    return login("admin")


@pytest.fixture
def anon():
    return TestClient(RouteRecorder(app), headers={"X-Requested-With": "psa"})


@pytest.fixture
def make_org(admin):
    def _make(name="Acme Corp", **kw):
        r = admin.post("/api/organizations", json={"name": name, **kw})
        assert r.status_code == 201, r.text
        return r.json()

    return _make


@pytest.fixture
def org_ctx(admin, make_org):
    """An organization with a contact, ready to have tickets."""
    org = make_org("Acme Corp")
    contact = admin.post(
        f"/api/organizations/{org['id']}/contacts",
        json={"name": "Pat Customer", "email": "pat@acme.com"},
    ).json()
    return {"org": org["id"], "contact": contact["id"]}


@pytest.fixture
def make_ticket(admin, org_ctx):
    def _make(**kw):
        body = {"organization_id": org_ctx["org"], "subject": "Printer down", **kw}
        r = admin.post("/api/tickets", json=body)
        assert r.status_code == 201, r.text
        return r.json()

    return _make


# ---- Phase 3 helpers ----
from datetime import datetime as _dt  # noqa: E402
from zoneinfo import ZoneInfo as _ZI  # noqa: E402


def biz_today():
    """'Today' in the default business timezone, matching the service layer."""
    return _dt.now(_ZI("America/Chicago")).date()


@pytest.fixture
def company(admin):
    r = admin.patch(
        "/api/settings",
        json={
            "company_name": "Acme MSP LLC",
            "company_address": "1 Main St\nSpringfield, IL",
            "invoice_footer": "Pay by ACH within terms.",
        },
    )
    assert r.status_code == 200, r.text


@pytest.fixture
def biller(login):
    return login("billing")


@pytest.fixture
def wt(admin):
    """Work type ids by name, with Remote=$150/h (not taxable), Onsite=$200/h (taxable)."""
    ids = {w["name"]: w["id"] for w in admin.get("/api/work-types").json()}
    assert (
        admin.patch(
            f"/api/billing/work-types/{ids['Remote']}", json={"rate_cents": 15000}
        ).status_code
        == 200
    )
    assert (
        admin.patch(
            f"/api/billing/work-types/{ids['Onsite']}", json={"rate_cents": 20000, "taxable": True}
        ).status_code
        == 200
    )
    return ids


@pytest.fixture
def log(admin):
    def _log(ticket_id, work_type_id, minutes, **kw):
        r = admin.post(
            f"/api/tickets/{ticket_id}/time",
            json={"work_type_id": work_type_id, "minutes": minutes, **kw},
        )
        assert r.status_code == 201, r.text
        return r.json()

    return _log


@pytest.fixture
def make_org_with_ticket(admin, make_org):
    def _make(name):
        org = make_org(name)
        t = admin.post(
            "/api/tickets", json={"organization_id": org["id"], "subject": f"{name} issue"}
        ).json()
        return org, t

    return _make


# ---- shared by the notice / statement tests ----
from datetime import timedelta as _td  # noqa: E402

from app import notices as _nsvc  # noqa: E402
from app.mail import ingest as _ingest  # noqa: E402
from tests.mailfakes import MAILBOX as _MAILBOX  # noqa: E402


@pytest.fixture
def mail_ready():
    """The worker has reported a configured mailbox, so sending is allowed."""
    _ingest.heartbeat(_MAILBOX)


@pytest.fixture
def client_org(admin, make_org, company):
    """A client whose billing contact will receive notices."""
    org = make_org("Acme Corp")["id"]
    admin.post(
        f"/api/organizations/{org}/contacts",
        json={"name": "Pat Payer", "email": "pat@acme.com", "is_billing_contact": True},
    )
    return org


@pytest.fixture
def clock(monkeypatch):
    """Move 'today' for the reminder logic: clock(days_after_real_today)."""

    def _set(days: int):
        monkeypatch.setattr(_nsvc, "today", lambda ctx: biz_today() + _td(days=days))

    return _set
