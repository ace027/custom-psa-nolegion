"""Immutability is enforced by PostgreSQL triggers, not just by Python: these tests bypass the
API entirely and talk to the database as the runtime role."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app import repositories as repo
from app.billing_repo import get_invoice, invoice_lines, list_invoices
from app.db import new_session, set_org_scope
from app.scope import Scope


@pytest.fixture
def final_invoice(biller, org_ctx, company):
    inv = biller.post(
        "/api/invoices", json={"organization_id": org_ctx["org"], "include_unbilled": False}
    ).json()
    biller.post(
        f"/api/invoices/{inv['id']}/lines",
        json={"description": "Consulting", "quantity": "1", "unit_price_cents": 10000},
    )
    done = biller.post(f"/api/invoices/{inv['id']}/finalize", json={}).json()
    return done["id"]


@pytest.fixture
def draft_invoice(biller, org_ctx):
    inv = biller.post(
        "/api/invoices", json={"organization_id": org_ctx["org"], "include_unbilled": False}
    ).json()
    biller.post(
        f"/api/invoices/{inv['id']}/lines",
        json={"description": "Consulting", "quantity": "1", "unit_price_cents": 10000},
    )
    return inv["id"]


def run_sql(sql: str, **params):
    with new_session() as db:
        set_org_scope(db, "all")
        try:
            db.execute(text(sql), params)
            db.commit()
        finally:
            db.rollback()


def refuses(sql: str, message: str, **params):
    with pytest.raises(DBAPIError, match=message):
        run_sql(sql, **params)


# ---- finalized invoices ----
@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE invoices SET total_cents = 1, subtotal_cents = 1 WHERE id = :i",
        "UPDATE invoices SET memo = 'tampered' WHERE id = :i",
        "UPDATE invoices SET status = 'draft' WHERE id = :i",
        "UPDATE invoices SET number = 'INV-9999-0001' WHERE id = :i",
        "UPDATE invoices SET due_date = due_date + 30 WHERE id = :i",
    ],
)
def test_a_final_invoice_cannot_be_edited_or_reopened(final_invoice, sql):
    refuses(sql, "immutable|only the void fields", i=final_invoice)


def test_a_final_invoice_can_only_move_to_void_and_only_changing_void_fields(final_invoice):
    refuses(
        "UPDATE invoices SET status = 'void', voided_at = now(), total_cents = 0, "
        "subtotal_cents = 0 WHERE id = :i",
        "only the void fields",
        i=final_invoice,
    )
    # a clean void is allowed
    run_sql(
        "UPDATE invoices SET status = 'void', voided_at = now(), void_reason = 'test' "
        "WHERE id = :i",
        i=final_invoice,
    )


def test_invoices_can_never_be_deleted(final_invoice, draft_invoice):
    for i in (final_invoice, draft_invoice):
        with pytest.raises(DBAPIError):  # no DELETE grant, and the trigger refuses anyway
            run_sql("DELETE FROM invoices WHERE id = :i", i=i)


def test_lines_of_a_final_invoice_are_frozen(final_invoice):
    refuses(
        "UPDATE invoice_lines SET amount_cents = 1 WHERE invoice_id = :i",
        "immutable",
        i=final_invoice,
    )
    refuses("DELETE FROM invoice_lines WHERE invoice_id = :i", "draft invoice", i=final_invoice)
    refuses(
        "INSERT INTO invoice_lines (invoice_id, organization_id, kind, description, quantity, "
        "unit_price_cents, amount_cents) SELECT id, organization_id, 'manual', 'sneaky', 1, 1, 1 "
        "FROM invoices WHERE id = :i",
        "draft invoice",
        i=final_invoice,
    )
    refuses(
        "UPDATE invoice_lines SET voided = true WHERE invoice_id = :i", "immutable", i=final_invoice
    )  # not even the void flag, while the invoice is still final


def test_voiding_only_permits_flagging_lines_voided(final_invoice):
    run_sql(
        "UPDATE invoices SET status = 'void', voided_at = now(), void_reason = 'x' WHERE id = :i",
        i=final_invoice,
    )
    # lines: only the 'voided' flag may change, and only false -> true
    refuses(
        "UPDATE invoice_lines SET amount_cents = 5 WHERE invoice_id = :i",
        "immutable",
        i=final_invoice,
    )
    refuses(
        "UPDATE invoices SET void_reason = 'edited' WHERE id = :i", "immutable", i=final_invoice
    )
    run_sql("UPDATE invoice_lines SET voided = true WHERE invoice_id = :i", i=final_invoice)


def test_a_void_invoice_is_frozen_forever(final_invoice):
    run_sql(
        "UPDATE invoices SET status = 'void', voided_at = now(), void_reason = 'x' WHERE id = :i",
        i=final_invoice,
    )
    refuses("UPDATE invoices SET status = 'final' WHERE id = :i", "immutable", i=final_invoice)
    refuses("UPDATE invoices SET memo = 'x' WHERE id = :i", "immutable", i=final_invoice)


# ---- drafts stay editable (the guard must not over-block) ----
def test_a_draft_invoice_and_its_lines_are_freely_editable(draft_invoice):
    run_sql(
        "UPDATE invoices SET memo = 'ok', subtotal_cents = 5, total_cents = 5 WHERE id = :i",
        i=draft_invoice,
    )
    run_sql("UPDATE invoice_lines SET amount_cents = 5 WHERE invoice_id = :i", i=draft_invoice)
    run_sql("DELETE FROM invoice_lines WHERE invoice_id = :i", i=draft_invoice)


# ---- table constraints ----
def test_constraints_protect_the_arithmetic_and_the_finalization_contract(draft_invoice):
    refuses(
        "UPDATE invoices SET total_cents = subtotal_cents + tax_cents + 1 WHERE id = :i",
        "ck_invoices_total",
        i=draft_invoice,
    )
    refuses("UPDATE invoices SET status = 'final' WHERE id = :i", "ck_invoices_", i=draft_invoice)


def test_runtime_role_cannot_delete_anything_in_the_billing_ledger(final_invoice, biller):
    for table in (
        "invoices",
        "agreement_quantity_log",
        "billing_runs",
        "invoice_counters",
        "product_charges",
    ):
        with pytest.raises(DBAPIError, match="permission denied"):
            run_sql(f"DELETE FROM {table}")
    with pytest.raises(DBAPIError, match="permission denied"):
        run_sql("UPDATE agreement_quantity_log SET new_quantity = 1")  # append-only
    assert biller  # fixture kept for clarity


# ---- isolation for the new tables (RLS + app-layer scope) ----
@pytest.fixture
def two_orgs_with_invoices(admin, biller, make_org, company):
    out = []
    for name in ("Org A", "Org B"):
        org = make_org(name)
        inv = biller.post(
            "/api/invoices", json={"organization_id": org["id"], "include_unbilled": False}
        ).json()
        biller.post(
            f"/api/invoices/{inv['id']}/lines", json={"description": "x", "unit_price_cents": 100}
        )
        biller.post(
            "/api/agreements",
            json={
                "organization_id": org["id"],
                "name": "MS",
                "type": "flat",
                "unit_price_cents": 100,
                "start_date": "2026-01-01",
            },
        )
        out.append((org["id"], inv["id"]))
    return out


@pytest.mark.parametrize(
    "table", ["invoices", "invoice_lines", "agreements", "agreement_quantity_log"]
)
def test_rls_scopes_billing_tables(two_orgs_with_invoices, table):
    (a, _), (b, _) = two_orgs_with_invoices
    with new_session() as db:
        assert db.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() == 0  # no scope
        set_org_scope(db, str(a))
        orgs = {r[0] for r in db.execute(text(f"SELECT organization_id FROM {table}"))}
        assert orgs == {a}
        set_org_scope(db, f"{a},{b}")
        assert {r[0] for r in db.execute(text(f"SELECT organization_id FROM {table}"))} == {a, b}


def test_repository_scope_hides_other_clients_invoices(two_orgs_with_invoices):
    (a, ia), (b, ib) = two_orgs_with_invoices
    with new_session() as db:
        set_org_scope(db, "all")  # RLS open: only the app-layer Scope filters
        scope = Scope.orgs(a)
        assert get_invoice(db, scope, ia) is not None and get_invoice(db, scope, ib) is None
        assert invoice_lines(db, scope, ib) == []
        items, total = list_invoices(
            db, scope, org_id=None, status=None, run_id=None, limit=50, offset=0
        )
        assert [i.id for i in items] == [ia] and total == 1
        assert repo.get_organization(db, scope, b) is None
