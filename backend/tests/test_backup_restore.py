"""Restore drill: dump the database, restore into a scratch DB, verify data AND security
settings (RLS, append-only grants) survive. Catches "backups exist but can't be restored"."""

import shutil
import subprocess

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

from tests.conftest import HOST, NAME, PORT

pytestmark = pytest.mark.skipif(not shutil.which("pg_dump"), reason="pg_dump not installed")

SCRATCH = "psa_restore_drill"


def test_dump_and_restore_preserves_data_and_security(admin, make_org, owner_engine):
    make_org("Backed Up Co")
    url = make_url(owner_engine.url.render_as_string(hide_password=False))
    env = {"PGPASSWORD": url.password, "PATH": "/usr/bin:/bin:/usr/local/bin"}
    conn = ["-h", HOST, "-p", PORT, "-U", url.username]

    dump = subprocess.run(
        ["pg_dump", *conn, "-d", NAME, "--format=custom"], env=env, capture_output=True, check=True
    ).stdout

    with create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT").connect() as c:
        c.execute(text(f"DROP DATABASE IF EXISTS {SCRATCH}"))
        c.execute(text(f"CREATE DATABASE {SCRATCH}"))
    try:
        subprocess.run(
            ["pg_restore", *conn, "-d", SCRATCH, "--no-owner", "--exit-on-error"],
            env=env,
            input=dump,
            capture_output=True,
            check=True,
        )
        scratch = create_engine(url.set(database=SCRATCH), poolclass=NullPool)
        with scratch.connect() as c:
            assert c.execute(text("SELECT name FROM organizations")).scalar_one() == "Backed Up Co"
            assert c.execute(text("SELECT count(*) FROM audit_log")).scalar_one() >= 1
            forced = c.execute(
                text(
                    "SELECT bool_and(relrowsecurity AND relforcerowsecurity) FROM pg_class "
                    "WHERE relname IN ('organizations','sites','contacts')"
                )
            ).scalar_one()
            assert forced is True
            policies = c.execute(text("SELECT count(*) FROM pg_policies")).scalar_one()
            assert policies == 3
            assert (
                c.execute(
                    text("SELECT has_table_privilege('psa_app','audit_log','UPDATE')")
                ).scalar_one()
                is False
            )
    finally:
        with create_engine(
            url.set(database="postgres"), isolation_level="AUTOCOMMIT"
        ).connect() as c:
            c.execute(text(f"DROP DATABASE IF EXISTS {SCRATCH}"))
